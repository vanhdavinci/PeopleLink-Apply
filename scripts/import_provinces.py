"""One-shot: import provinces from provincedata.text HTML select into SQLite."""
from __future__ import annotations

import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import get_conn, init_db
from app.services.location_sync import BAD_PROVINCE_CODES

SOURCE = ROOT / "provincedata.text"
OPTION_RE = re.compile(
    r'<option\s+value="([^"]*)"[^>]*>(.*?)</option>',
    re.IGNORECASE | re.DOTALL,
)


def main() -> None:
    init_db()
    text = html.unescape(SOURCE.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    skipped_bad = 0
    skipped_numeric = 0
    for m in OPTION_RE.finditer(text):
        inserted_value = m.group(1).strip()
        label = re.sub(r"\s+", " ", m.group(2)).strip()
        if not inserted_value or "|" not in inserted_value:
            continue
        code, name_from_value = inserted_value.split("|", 1)
        code = code.strip()
        name = (label or name_from_value).strip()
        if code in BAD_PROVINCE_CODES:
            skipped_bad += 1
            print(f"skip bad code: {code}")
            continue
        # Chỉ giữ mã chữ — sync Area + dropdown apply dùng ANGIANG/HANOI/...
        if not code or not code[0].isalpha():
            skipped_numeric += 1
            continue
        if code in seen:
            print(f"skip duplicate code: {code}")
            continue
        seen.add(code)
        rows.append((code, name, inserted_value, now))

    with get_conn() as conn:
        conn.execute("DELETE FROM provinces")
        conn.executemany(
            """
            INSERT INTO provinces (code, name, inserted_value, synced_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM provinces").fetchone()["c"]
        letter = conn.execute(
            "SELECT COUNT(*) AS c FROM provinces WHERE code GLOB '[A-Z]*'"
        ).fetchone()["c"]

    print(f"Imported {count} provinces from {SOURCE.name}")
    print(f"  letter codes: {letter}")
    print(f"  skipped bad: {skipped_bad}")
    print(f"  skipped numeric: {skipped_numeric}")


if __name__ == "__main__":
    main()
