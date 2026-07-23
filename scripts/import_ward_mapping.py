"""Import ward_mapping_old_to_new.csv into SQLite."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import init_db
from app.services.ward_mapping import DEFAULT_MAPPING_CSV, import_ward_mapping_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Import ward old↔new mapping CSV")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_MAPPING_CSV,
        help=f"Path to CSV (default: {DEFAULT_MAPPING_CSV})",
    )
    args = parser.parse_args()
    init_db()
    result = import_ward_mapping_csv(args.csv)
    print(
        f"OK — inserted={result.inserted} "
        f"(MAPPED={result.mapped}, DIVIDED={result.divided}, "
        f"NOT_FOUND={result.not_found}) from {result.path}"
    )


if __name__ == "__main__":
    main()
