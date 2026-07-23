"""CLI: sync projects (+ members) and mark expired."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import db_stats, init_db
from app.services.project_sync import mark_expired_projects, sync_projects


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync portal projects into SQLite")
    parser.add_argument(
        "--cookie",
        help="Portal Cookie header value (or use PEOPLELINK_PORTAL_COOKIE / settings)",
    )
    parser.add_argument(
        "--save-cookie",
        action="store_true",
        help="Persist --cookie into settings for later button syncs",
    )
    parser.add_argument(
        "--from-json",
        type=Path,
        help="Skip API; upsert from a JSON file (array or {Data:[...]})",
    )
    parser.add_argument(
        "--mark-expired-only",
        action="store_true",
        help="Only recompute is_expired flags",
    )
    args = parser.parse_args()

    init_db()

    if args.mark_expired_only:
        result = mark_expired_projects()
        print(
            f"Marked expired={result.expired_count} "
            f"cleared={result.unexpired_count} "
            f"total_expired_now={result.project_count}"
        )
        return

    items = None
    if args.from_json:
        payload = json.loads(args.from_json.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            items = payload.get("Data") or payload.get("data") or [payload]
        else:
            items = payload

    result = sync_projects(
        cookie=args.cookie,
        items=items,
        save_cookie=args.save_cookie,
        progress=lambda msg: print(msg, flush=True),
    )
    stats = db_stats()
    print(
        f"Done. projects={result.project_count} members={result.member_count} "
        f"newly_expired={result.expired_count} unexpired={result.unexpired_count}"
    )
    print(
        f"DB: projects={stats['projects']} members={stats['project_members']} "
        f"expired={stats['projects_expired']}"
    )
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors[:20]:
            print(" -", err)


if __name__ == "__main__":
    main()
