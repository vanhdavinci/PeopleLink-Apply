"""CLI: sync districts + wards from location API into SQLite."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import db_stats, init_db
from app.services.location_sync import purge_bad_provinces, sync_locations


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync city/district + ward into SQLite")
    parser.add_argument(
        "--province",
        action="append",
        dest="provinces",
        help="Only sync these province codes (repeatable). Default: all letter codes.",
    )
    parser.add_argument(
        "--all-codes",
        action="store_true",
        help="Also try numeric province codes (01, 79, ...).",
    )
    parser.add_argument(
        "--districts-only",
        action="store_true",
        help="Skip ward sync.",
    )
    parser.add_argument(
        "--keep-bad",
        action="store_true",
        help="Do not purge QUYNHON / numeric codes before sync.",
    )
    args = parser.parse_args()

    init_db()
    if not args.keep_bad and args.provinces is None:
        removed = purge_bad_provinces()
        if removed:
            print(f"Purged {len(removed)} bad/numeric provinces: {', '.join(removed)}")
    print("Starting location sync...")
    result = sync_locations(
        province_codes=args.provinces,
        letter_codes_only=not args.all_codes,
        sync_wards=not args.districts_only,
        # CLI đã purge phía trên — tránh xóa 2 lần
        purge_bad=False,
        progress=lambda msg: print(msg, flush=True),
    )
    stats = db_stats()
    print(
        f"Done. provinces_ok={result.province_count} "
        f"districts={result.district_count} wards={result.ward_count}"
    )
    print(
        f"DB counts: provinces={stats['provinces']} "
        f"districts={stats['districts']} wards={stats['wards']}"
    )
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors[:20]:
            print(" -", err)


if __name__ == "__main__":
    main()
