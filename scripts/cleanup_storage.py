#!/usr/bin/env python3
"""
cleanup_storage — safe lifecycle cleanup for Presentation storage.

Passes, in order:
  1. mark-orphaned    — presentations with no referencing session and no
                         orphaned_since mark yet get the mark set now. Covers
                         both fresh detach/replace events and legacy rows
                         that predate the mark existing at all.
  2. delete-expired   — presentations orphaned past the retention window,
                         still unreferenced at sweep time (re-checked to
                         avoid a race with a concurrent re-attach), get
                         deleted: DB rows + every known storage key.
  3. disk-orphan sweep — presentation directories on disk with zero matching
                         DB row at all (e.g. a crashed/failed upload) get
                         removed, skipping anything younger than 1 hour so an
                         in-flight upload is never touched.
  4. stuck-processing — PENDING/PROCESSING rows older than 1 hour (should
                         never happen since processing is synchronous within
                         one request — no task queue exists — but defensive)
                         get marked FAILED.

Never deletes anything still referenced by a Session. Mirrors the
conventions of scripts/repair_uploaded_slides.py: argparse, --dry-run, a
direct asyncpg connection (no app event-loop/session machinery needed for a
one-shot script).

Usage:
    python scripts/cleanup_storage.py [--dry-run] [--retention-days N] [--verbose]
"""
import argparse
import asyncio
import logging
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger("cleanup_storage")


def _load_database_url() -> str:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return val
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Set it in .env or as an environment variable."
        )
    return url


async def _mark_orphaned(conn, dry_run: bool) -> int:
    rows = await conn.fetch(
        """
        SELECT p.id FROM presentations p
        WHERE p.orphaned_since IS NULL
          AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.presentation_id = p.id)
        """
    )
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    logger.info(
        "Marking %d newly-unreferenced presentation(s) as orphaned%s",
        len(ids), " [DRY RUN]" if dry_run else "",
    )
    if not dry_run:
        await conn.execute(
            "UPDATE presentations SET orphaned_since = now() WHERE id = ANY($1::uuid[])", ids
        )
    return len(ids)


async def _delete_expired(conn, retention_days: int, dry_run: bool, storage) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    rows = await conn.fetch(
        """
        SELECT p.id, p.owner_id, p.original_file_url
        FROM presentations p
        WHERE p.orphaned_since IS NOT NULL
          AND p.orphaned_since < $1
          AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.presentation_id = p.id)
        """,
        cutoff,
    )
    deleted = 0
    for row in rows:
        pres_id = row["id"]
        page_rows = await conn.fetch(
            "SELECT image_url, thumbnail_url FROM presentation_pages WHERE presentation_id = $1",
            pres_id,
        )
        keys = (
            [row["original_file_url"]]
            + [pr["image_url"] for pr in page_rows]
            + [pr["thumbnail_url"] for pr in page_rows]
        )

        logger.info(
            "Deleting expired presentation %s (owner=%s, orphaned past %d days)%s",
            pres_id, row["owner_id"], retention_days, " [DRY RUN]" if dry_run else "",
        )
        if not dry_run:
            await conn.execute("DELETE FROM presentations WHERE id = $1", pres_id)
            for key in keys:
                storage.delete(key)
            storage.delete_prefix(f"presentations/{row['owner_id']}/{pres_id}")
        deleted += 1
    return deleted


def _sweep_disk_orphans(known_ids: set[str], storage_root: Path, dry_run: bool) -> int:
    """
    Handles both directory shapes: old (`presentations/<uuid>/`) and new
    (`presentations/<owner_uuid>/<presentation_uuid>/`) — a first path
    segment that isn't a UUID is treated as an owner directory and searched
    one level deeper.
    """
    presentations_dir = storage_root / "presentations"
    if not presentations_dir.is_dir():
        return 0

    grace_cutoff = datetime.now().timestamp() - 3600  # skip anything younger than 1h
    removed = 0

    def maybe_remove(dir_path: Path) -> bool:
        if dir_path.name in known_ids:
            return False
        try:
            mtime = dir_path.stat().st_mtime
        except OSError:
            return False
        if mtime > grace_cutoff:
            return False  # could be an in-flight upload — leave it alone
        logger.info(
            "Removing disk-orphaned directory %s (no matching DB row)%s",
            dir_path, " [DRY RUN]" if dry_run else "",
        )
        if not dry_run:
            shutil.rmtree(dir_path, ignore_errors=True)
        return True

    for entry in presentations_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            uuid.UUID(entry.name)
        except ValueError:
            # Not a UUID — treat as an owner_id directory, recurse one level.
            for sub in entry.iterdir():
                if not sub.is_dir():
                    continue
                try:
                    uuid.UUID(sub.name)
                except ValueError:
                    continue
                if maybe_remove(sub):
                    removed += 1
            continue
        if maybe_remove(entry):
            removed += 1

    return removed


async def _mark_stuck_failed(conn, dry_run: bool) -> int:
    rows = await conn.fetch(
        """
        SELECT id FROM presentations
        WHERE status IN ('PENDING', 'PROCESSING') AND created_at < now() - interval '1 hour'
        """
    )
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    logger.info(
        "Marking %d stuck PENDING/PROCESSING presentation(s) as FAILED%s",
        len(ids), " [DRY RUN]" if dry_run else "",
    )
    if not dry_run:
        await conn.execute("UPDATE presentations SET status = 'FAILED' WHERE id = ANY($1::uuid[])", ids)
    return len(ids)


async def _run(args: argparse.Namespace) -> None:
    import asyncpg

    from app.config import get_settings
    from app.storage import get_storage_backend

    settings = get_settings()
    retention_days = (
        args.retention_days
        if args.retention_days is not None
        else settings.PRESENTATION_ORPHAN_RETENTION_DAYS
    )

    db_url = _load_database_url()
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    logger.info("Connected to database. retention_days=%d dry_run=%s", retention_days, args.dry_run)

    try:
        storage = get_storage_backend()
        marked = await _mark_orphaned(conn, args.dry_run)
        deleted = await _delete_expired(conn, retention_days, args.dry_run, storage)

        known_ids = {str(r["id"]) for r in await conn.fetch("SELECT id FROM presentations")}
        disk_removed = _sweep_disk_orphans(known_ids, Path(settings.STORAGE_ROOT).resolve(), args.dry_run)

        stuck = await _mark_stuck_failed(conn, args.dry_run)
    finally:
        await conn.close()

    label = "would_" if args.dry_run else ""
    logger.info(
        "Done. %smark_orphaned=%d %sdelete_expired=%d %sdisk_orphans_removed=%d %smark_stuck_failed=%d",
        label, marked, label, deleted, label, disk_removed, label, stuck,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safe lifecycle cleanup for Presentation storage — orphan marking, "
        "retention-window deletion, disk-orphan sweep, stuck-processing sweep."
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would change; make no writes.")
    parser.add_argument(
        "--retention-days", type=int, default=None,
        help="Override PRESENTATION_ORPHAN_RETENTION_DAYS for this run.",
    )
    parser.add_argument("--verbose", action="store_true", help="Log at DEBUG level.")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
