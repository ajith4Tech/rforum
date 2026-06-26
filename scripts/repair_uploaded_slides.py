#!/usr/bin/env python3
"""
repair_uploaded_slides — Scan and repair slides with incorrect page counts.

Finds all CONTENT slides where total_pages == 1 (or is missing) but the
attached file has more pages. Optionally re-runs LibreOffice conversion for
stranded PPT/PPTX files.

Usage:
    python scripts/repair_uploaded_slides.py [--dry-run] [--slide-id UUID]

Options:
    --dry-run      Print what would change; make no database writes.
    --slide-id ID  Repair a single slide by ID instead of scanning all.
    --convert      Re-attempt LibreOffice conversion for .ppt/.pptx files.
    --verbose      Log detailed progress for every slide checked.

Environment:
    DATABASE_URL   asyncpg connection string (read from .env or environment).
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# Allow running from the project root: python scripts/repair_uploaded_slides.py
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
)
logger = logging.getLogger("repair")


def _load_database_url() -> str:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                # asyncpg driver required
                return val
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Set it in .env or as an environment variable."
        )
    return url


async def _repair(args: argparse.Namespace) -> None:
    import asyncpg

    from app.services.file_processing import convert_to_pdf_if_needed, extract_total_pages

    db_url = _load_database_url()
    # asyncpg uses postgresql:// scheme, not postgresql+asyncpg://
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(pg_url)
    logger.info("Connected to database.")

    try:
        if args.slide_id:
            rows = await conn.fetch(
                """
                SELECT id, content_json
                FROM slides
                WHERE id = $1 AND type = 'CONTENT'
                """,
                args.slide_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, content_json
                FROM slides
                WHERE type = 'CONTENT'
                  AND content_json IS NOT NULL
                  AND content_json ->> 'file_url' IS NOT NULL
                  AND content_json ->> 'file_url' != ''
                ORDER BY id
                """
            )

        total = len(rows)
        logger.info("Found %d CONTENT slide(s) to inspect.", total)

        repaired = 0
        skipped = 0
        errored = 0

        for row in rows:
            slide_id = str(row["id"])
            cj: dict = json.loads(row["content_json"]) if isinstance(row["content_json"], str) else dict(row["content_json"])

            file_url: str = cj.get("file_url", "")
            stored_pages: int = cj.get("total_pages", 1)
            file_name: str = cj.get("file_name", "")

            if not file_url:
                if args.verbose:
                    logger.info("SKIP  slide=%s — no file_url", slide_id)
                skipped += 1
                continue

            file_path = file_url.lstrip("/")
            if not os.path.exists(file_path):
                logger.warning("SKIP  slide=%s — file not found on disk: '%s'", slide_id, file_path)
                skipped += 1
                continue

            ext = Path(file_path).suffix.lower()

            # ── Optional: re-attempt conversion for stranded PPT/PPTX ────────
            if args.convert and ext in {".ppt", ".pptx"}:
                logger.info("CONV  slide=%s — attempting LibreOffice conversion for '%s'", slide_id, file_path)
                conversion = convert_to_pdf_if_needed(file_path, ext)
                if conversion.success and conversion.output_path:
                    pdf_basename = os.path.basename(conversion.output_path)
                    new_url = f"/uploads/{pdf_basename}"
                    cj["file_url"] = new_url
                    cj["file_name"] = pdf_basename
                    cj["file_type"] = "application/pdf"
                    file_path = conversion.output_path
                    file_url = new_url
                    logger.info("      Converted → '%s'", conversion.output_path)
                else:
                    for w in conversion.warnings:
                        logger.warning("      %s", w)

            # ── Extract real page count ────────────────────────────────────
            actual_pages, page_warnings = extract_total_pages(file_path)
            for w in page_warnings:
                logger.warning("      slide=%s page warning: %s", slide_id, w)

            if actual_pages == stored_pages and cj.get("file_url") == file_url:
                if args.verbose:
                    logger.info("OK    slide=%s — pages=%d, no change needed", slide_id, actual_pages)
                skipped += 1
                continue

            logger.info(
                "REPAIR slide=%s — pages: %d → %d | file_url: '%s' → '%s'%s",
                slide_id,
                stored_pages, actual_pages,
                cj.get("file_url", ""), file_url,
                " [DRY RUN]" if args.dry_run else "",
            )

            if not args.dry_run:
                cj["total_pages"] = actual_pages
                cj["file_url"] = file_url
                if "file_name" in cj:
                    cj["file_name"] = os.path.basename(file_url)
                try:
                    await conn.execute(
                        "UPDATE slides SET content_json = $1 WHERE id = $2",
                        json.dumps(cj),
                        row["id"],
                    )
                    repaired += 1
                except Exception as exc:
                    logger.error("ERROR slide=%s — DB update failed: %s", slide_id, exc)
                    errored += 1
            else:
                repaired += 1  # counts "would repair" in dry-run

    finally:
        await conn.close()

    label = "Would repair" if args.dry_run else "Repaired"
    logger.info(
        "Done. %s=%d  skipped=%d  errored=%d  (dry_run=%s)",
        label, repaired, skipped, errored, args.dry_run,
    )
    if args.dry_run and repaired:
        logger.info("Re-run without --dry-run to apply changes.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair slides with incorrect page counts or stranded PPT/PPTX files."
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would change; do not write.")
    parser.add_argument("--slide-id", metavar="UUID", help="Repair a single slide by ID.")
    parser.add_argument("--convert", action="store_true", help="Re-attempt LibreOffice conversion for .ppt/.pptx.")
    parser.add_argument("--verbose", action="store_true", help="Log every slide inspected.")
    args = parser.parse_args()

    asyncio.run(_repair(args))


if __name__ == "__main__":
    main()
