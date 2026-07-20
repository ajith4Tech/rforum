#!/usr/bin/env python3
"""
migrate_presentations_to_s3 — backfill locally-stored presentation assets
into S3 ahead of (or during) the STORAGE_PROVIDER=local -> s3 switchover.

DB-driven: iterates every Presentation (+ its PresentationPage rows) rather
than walking the local filesystem. The database's *_url columns are the
single source of truth for what key a piece of content is addressed by
(app/routers/presentations.py reads them as literal strings, never
reconstructs them) — walking the filesystem instead would (a) upload
whatever stray/orphaned directories happen to sit under STORAGE_ROOT with
no backing DB row, using an S3 key the app will never actually request, and
(b) silently miss the actual per-presentation picture (skip counts, missing
assets) since a bare file listing can't tell a real gap from an
intentionally-absent lazy cache.

For each presentation, four asset categories are considered:
  - original   presentation.original_file_url            — always expected.
  - pdf        derived cache key (pdf_key_for_dir)         — only expected for
                                                              PPT/PPTX sources;
                                                              lazily created on
                                                              first render, so
                                                              routinely absent.
  - thumbnails page.thumbnail_url for every page           — eagerly created at
                                                              upload time; a
                                                              missing one is a
                                                              real data problem.
  - pages      page.image_url for every page               — full-res renders
                                                              are lazy (cached
                                                              on first view),
                                                              so routinely
                                                              absent for decks
                                                              nobody has opened.

Assets missing locally are recorded (not treated as failures) — "pdf" and
"pages" gaps are expected/routine and logged at DEBUG; a missing "original"
or "thumbnails" asset is a genuine data-integrity problem and is always
reported in the final summary.

For each asset actually present on disk:
  - HEAD the equivalent S3 object.
  - Missing entirely       -> upload.
  - Present, checksum      -> verified (ETag matches the local file's MD5,
    matches                   for the common non-multipart-upload case)
                               -> skip.
  - Present, checksum       -> re-upload for correctness. Also logged when the
    mismatches / can't be       remote ETag is a multipart-style ETag (contains
    verified via plain MD5      '-'), where a single-part MD5 comparison isn't
                                 valid — falls back to a size-only comparison
                                 and flags it for manual review.

The whole run is idempotent by construction (every asset is independently
skip-if-already-there), so it's resumable for free: killing it midway and
re-running just re-checks and skips everything already uploaded. No separate
progress/state file is needed or created.

Usage:
    python scripts/migrate_presentations_to_s3.py [--dry-run] [--verbose] [--limit N]

Requires STORAGE_PROVIDER-independent config to already be set (S3_BUCKET,
S3_REGION, S3_PREFIX, AWS credentials) regardless of what STORAGE_PROVIDER
currently is — this script talks to S3 directly rather than through
get_storage_backend(), since it needs ETag/size comparisons that only make
sense for the S3 side. It also reads local files directly through
LocalFilesystemBackend (never through FallbackStorageBackend) so a
misconfigured STORAGE_PROVIDER can't accidentally make the "local" side of
the comparison silently read back from S3.
"""
import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger("migrate_presentations_to_s3")

# Asset categories where a local gap is routine (lazy caches) vs. a genuine
# data-integrity problem worth surfacing prominently.
_ROUTINE_MISSING_CATEGORIES = frozenset({"pdf", "page"})


@dataclass
class MigrationStats:
    presentations_total: int = 0
    presentations_migrated: int = 0     # >=1 asset actually uploaded this run
    presentations_skipped: int = 0      # fully present & verified already, nothing to do
    presentations_failed: int = 0       # >=1 asset upload/verify raised an error

    files_uploaded: int = 0
    files_skipped_verified: int = 0
    files_reuploaded_mismatch: int = 0
    files_unverified_multipart: int = 0
    bytes_uploaded: int = 0

    # (presentation_id, category, key) tuples
    missing_local_assets: list[tuple[str, str, str]] = field(default_factory=list)
    corrupted_assets: list[tuple[str, str, str]] = field(default_factory=list)
    failed_assets: list[tuple[str, str, str]] = field(default_factory=list)


def _md5_hex(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_assets(presentation, pages, pdf_key_for_dir, dir_prefix_from_known_key):
    """Yield (category, key) for every asset a presentation *could* have."""
    yield "original", presentation.original_file_url
    pres_dir = dir_prefix_from_known_key(presentation.original_file_url, presentation.id)
    yield "pdf", pdf_key_for_dir(pres_dir)
    for page in pages:
        yield "thumbnail", page.thumbnail_url
        yield "page", page.image_url


def _migrate_asset(s3_backend, local_backend, category: str, key: str, dry_run: bool) -> str:
    """Upload/verify a single asset already confirmed present on local disk.
    Returns one of: "uploaded", "skipped_verified", "reuploaded_mismatch",
    "unverified_multipart", "failed", "corrupted"."""
    path = local_backend.path_for(key)
    try:
        size = path.stat().st_size
    except OSError as exc:
        logger.error("migrate_local_read_failed key=%s error=%s", key, exc)
        return "corrupted"
    if size == 0:
        logger.warning("migrate_local_zero_byte key=%s — treating as corrupted, not uploading", key)
        return "corrupted"

    try:
        remote = s3_backend.head(key)
    except (ConnectionError, PermissionError) as exc:
        logger.error("migrate_head_failed key=%s error=%s", key, exc)
        return "failed"

    if remote is None:
        logger.info("migrate_upload category=%s key=%s size=%d%s", category, key, size, " [DRY RUN]" if dry_run else "")
        if not dry_run:
            try:
                s3_backend.save(key, path.read_bytes())
            except (ConnectionError, PermissionError, OSError) as exc:
                logger.error("migrate_upload_failed key=%s error=%s", key, exc)
                return "failed"
        return "uploaded"

    if "-" in remote["etag"]:
        if remote["size"] == size:
            logger.debug("migrate_skip_size_only key=%s size=%d (multipart ETag, unverified)", key, size)
            return "unverified_multipart"
        logger.warning(
            "migrate_size_mismatch key=%s local_size=%d remote_size=%d — re-uploading%s",
            key, size, remote["size"], " [DRY RUN]" if dry_run else "",
        )
        if not dry_run:
            try:
                s3_backend.save(key, path.read_bytes())
            except (ConnectionError, PermissionError, OSError) as exc:
                logger.error("migrate_upload_failed key=%s error=%s", key, exc)
                return "failed"
        return "reuploaded_mismatch"

    local_md5 = _md5_hex(path)
    if local_md5 == remote["etag"]:
        logger.debug("migrate_skip_verified key=%s", key)
        return "skipped_verified"

    logger.warning(
        "migrate_checksum_mismatch key=%s local_md5=%s remote_etag=%s — re-uploading%s",
        key, local_md5, remote["etag"], " [DRY RUN]" if dry_run else "",
    )
    if not dry_run:
        try:
            s3_backend.save(key, path.read_bytes())
        except (ConnectionError, PermissionError, OSError) as exc:
            logger.error("migrate_upload_failed key=%s error=%s", key, exc)
            return "failed"
    return "reuploaded_mismatch"


async def _migrate_presentation(s3_backend, local_backend, presentation, pages, dry_run: bool,
                                 stats: MigrationStats, pdf_key_for_dir, dir_prefix_from_known_key) -> None:
    pres_id = str(presentation.id)
    by_category: dict[str, list[str]] = {}
    for category, key in _expected_assets(presentation, pages, pdf_key_for_dir, dir_prefix_from_known_key):
        by_category.setdefault(category, []).append(key)

    any_uploaded = False
    any_failed = False
    any_action_needed = False

    for category in ("original", "pdf", "thumbnail", "page"):
        keys = by_category.get(category, [])
        present_keys = [k for k in keys if local_backend.exists(k)]
        missing_keys = [k for k in keys if k not in present_keys]

        for key in missing_keys:
            entry = (pres_id, category, key)
            if category in _ROUTINE_MISSING_CATEGORIES:
                logger.debug("migrate_missing_local_routine presentation=%s category=%s key=%s", pres_id, category, key)
            else:
                logger.warning("migrate_missing_local presentation=%s category=%s key=%s", pres_id, category, key)
            stats.missing_local_assets.append(entry)

        if not present_keys:
            continue

        label = {"original": "original", "pdf": "pdf", "thumbnail": "thumbnails", "page": "pages"}[category]
        logger.info("  Uploading %s...", label)
        for key in present_keys:
            outcome = _migrate_asset(s3_backend, local_backend, category, key, dry_run)
            if outcome == "uploaded":
                stats.files_uploaded += 1
                stats.bytes_uploaded += local_backend.size(key)
                any_uploaded = True
                any_action_needed = True
            elif outcome == "skipped_verified":
                stats.files_skipped_verified += 1
            elif outcome == "reuploaded_mismatch":
                stats.files_reuploaded_mismatch += 1
                any_uploaded = True
                any_action_needed = True
            elif outcome == "unverified_multipart":
                stats.files_unverified_multipart += 1
            elif outcome == "corrupted":
                stats.corrupted_assets.append((pres_id, category, key))
                any_failed = True
            elif outcome == "failed":
                stats.failed_assets.append((pres_id, category, key))
                any_failed = True

    if any_failed:
        stats.presentations_failed += 1
    elif any_uploaded:
        stats.presentations_migrated += 1
    else:
        stats.presentations_skipped += 1

    logger.info("  Verified." if not any_failed else "  Completed with errors.")


async def _run(args: argparse.Namespace) -> MigrationStats:
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import async_session
    from app.models import Presentation, PresentationPage
    from app.storage.keys import dir_prefix_from_known_key, pdf_key_for_dir
    from app.storage.local import LocalFilesystemBackend
    from app.storage.s3 import S3StorageBackend

    settings = get_settings()
    if not settings.S3_BUCKET:
        raise RuntimeError("S3_BUCKET is not configured — set it in .env before migrating.")

    s3_backend = S3StorageBackend(
        bucket=settings.S3_BUCKET,
        region=settings.S3_REGION,
        prefix=settings.S3_PREFIX,
        endpoint_url=settings.S3_ENDPOINT or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        max_retries=settings.S3_MAX_RETRIES,
    )
    local_backend = LocalFilesystemBackend(root=settings.STORAGE_ROOT)

    # Preflight: fail fast with a clear message rather than crashing deep
    # into the first presentation's first asset (bucket typos / missing IAM
    # permissions are the two failure modes actually hit while wiring this
    # up — surface them before doing any real work).
    try:
        s3_backend.check_bucket_access()
    except (FileNotFoundError, PermissionError, ConnectionError) as exc:
        raise RuntimeError(
            f"S3 preflight check failed against bucket={settings.S3_BUCKET!r} "
            f"region={settings.S3_REGION!r}: {exc}. Verify S3_BUCKET is correct "
            "and the configured AWS credentials have s3:GetObject/PutObject/"
            "ListBucket on this bucket before migrating."
        ) from exc

    logger.info(
        "migration_start source=db bucket=%s prefix=%s dry_run=%s",
        settings.S3_BUCKET, settings.S3_PREFIX, args.dry_run,
    )

    stats = MigrationStats()
    async with async_session() as db:
        result = await db.execute(select(Presentation).order_by(Presentation.created_at))
        presentations = list(result.scalars().all())
        if args.limit is not None:
            presentations = presentations[: args.limit]
        stats.presentations_total = len(presentations)

        for i, presentation in enumerate(presentations, start=1):
            page_result = await db.execute(
                select(PresentationPage)
                .where(PresentationPage.presentation_id == presentation.id)
                .order_by(PresentationPage.page_number)
            )
            pages = list(page_result.scalars().all())

            logger.info("Presentation %d/%d (id=%s)", i, stats.presentations_total, presentation.id)
            await _migrate_presentation(
                s3_backend, local_backend, presentation, pages, args.dry_run, stats,
                pdf_key_for_dir, dir_prefix_from_known_key,
            )

    label = "would_" if args.dry_run else ""
    logger.info(
        "migration_done presentations=%d %smigrated=%d skipped=%d failed=%d "
        "files_%suploaded=%d skipped_verified=%d reuploaded_mismatch=%d "
        "unverified_multipart=%d bytes_%suploaded=%d missing_local=%d corrupted=%d",
        stats.presentations_total, label, stats.presentations_migrated, stats.presentations_skipped,
        stats.presentations_failed, label, stats.files_uploaded, stats.files_skipped_verified,
        stats.files_reuploaded_mismatch, stats.files_unverified_multipart, label, stats.bytes_uploaded,
        len(stats.missing_local_assets), len(stats.corrupted_assets),
    )
    if stats.failed_assets:
        logger.error("migration_failed_assets assets=%s", stats.failed_assets)
    if stats.missing_local_assets:
        non_routine = [a for a in stats.missing_local_assets if a[1] not in _ROUTINE_MISSING_CATEGORIES]
        if non_routine:
            logger.warning("migration_missing_local_assets_nonroutine assets=%s", non_routine)
    if stats.corrupted_assets:
        logger.error("migration_corrupted_assets assets=%s", stats.corrupted_assets)
    return stats


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(
        description="Backfill locally-stored presentation assets into S3, driven by the "
        "Presentation/PresentationPage tables. Idempotent and safe to re-run — "
        "already-uploaded, checksum-verified objects are skipped."
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would change; make no S3 writes.")
    parser.add_argument("--verbose", action="store_true", help="Log at DEBUG level (logs every skip too).")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N presentations (testing/staged rollout).")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    stats = asyncio.run(_run(args))
    sys.exit(1 if (stats.presentations_failed or stats.corrupted_assets) else 0)


if __name__ == "__main__":
    main()
