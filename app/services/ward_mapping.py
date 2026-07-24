"""Import + lookup ward address mapping (old/portal ↔ new admin)."""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import ROOT_DIR
from app.db import get_conn

DEFAULT_MAPPING_CSV = ROOT_DIR / "ward_mapping_old_to_new.csv"

_BOOL_TRUE = {"1", "true", "yes", "y", "t"}

_ADMIN_PREFIXES = (
    "thành phố ",
    "tp. ",
    "tp ",
    "tỉnh ",
    "quận ",
    "huyện ",
    "thị xã ",
    "thị trấn ",
    "phường ",
    "xã ",
    "p. ",
    "p ",
)


def _fold_vn(text: str) -> str:
    raw = unicodedata.normalize("NFD", (text or "").strip())
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    raw = re.sub(r"\s+", " ", raw)
    return raw.casefold()


def _strip_admin_prefix(text: str) -> str:
    t = (text or "").strip()
    lower = t.casefold()
    for prefix in _ADMIN_PREFIXES:
        if lower.startswith(prefix):
            return t[len(prefix) :].strip()
    return t


def _place_key(text: str) -> str:
    """Khóa so khớp: bỏ tiền tố hành chính + không dấu."""
    return _fold_vn(_strip_admin_prefix(text) or text)


def _cell(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return str(row[key]).strip()
    return ""


def _as_bool(value: str) -> int:
    return 1 if value.strip().lower() in _BOOL_TRUE else 0


@dataclass
class MappingImportResult:
    path: str
    inserted: int
    mapped: int
    divided: int
    not_found: int


def import_ward_mapping_csv(path: Path | None = None) -> MappingImportResult:
    """
    Replace ward_address_mappings from CSV.
    File: ward_mapping_old_to_new.csv (old/portal ↔ new 2-level).
    """
    csv_path = Path(path) if path else DEFAULT_MAPPING_CSV
    if not csv_path.is_file():
        raise FileNotFoundError(f"Không thấy file mapping: {csv_path}")

    rows: list[tuple[Any, ...]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            rows.append(
                (
                    _cell(raw, "name"),
                    _cell(raw, "inserted_value"),
                    _cell(raw, "name_normalized"),
                    _cell(raw, "match_status"),
                    _cell(raw, "mapping_type"),
                    _as_bool(_cell(raw, "is_default_new_ward")),
                    _cell(raw, "old_ward"),
                    _cell(raw, "old_district"),
                    _cell(raw, "old_province"),
                    _cell(raw, "old_ward_code"),
                    _cell(raw, "old_district_code"),
                    _cell(raw, "old_province_code"),
                    _cell(raw, "old_full_address"),
                    _cell(raw, "new_ward"),
                    _cell(raw, "new_province"),
                    _cell(raw, "new_ward_code"),
                    _cell(raw, "new_province_code"),
                    _cell(raw, "new_full_address"),
                    _cell(raw, "match_note"),
                )
            )

    with get_conn() as conn:
        conn.execute("DELETE FROM ward_address_mappings")
        conn.executemany(
            """
            INSERT INTO ward_address_mappings (
                portal_ward_name, portal_ward_value, name_normalized,
                match_status, mapping_type, is_default_new_ward,
                old_ward, old_district, old_province,
                old_ward_code, old_district_code, old_province_code,
                old_full_address,
                new_ward, new_province, new_ward_code, new_province_code,
                new_full_address, match_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        mapped = conn.execute(
            "SELECT COUNT(*) AS c FROM ward_address_mappings WHERE match_status = 'MAPPED'"
        ).fetchone()["c"]
        divided = conn.execute(
            "SELECT COUNT(*) AS c FROM ward_address_mappings WHERE match_status = 'MAPPED_DIVIDED'"
        ).fetchone()["c"]
        not_found = conn.execute(
            "SELECT COUNT(*) AS c FROM ward_address_mappings WHERE match_status = 'NOT_FOUND'"
        ).fetchone()["c"]

    return MappingImportResult(
        path=str(csv_path),
        inserted=len(rows),
        mapped=int(mapped),
        divided=int(divided),
        not_found=int(not_found),
    )


def mapping_stats() -> dict[str, int]:
    with get_conn() as conn:
        try:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM ward_address_mappings"
            ).fetchone()["c"]
        except Exception:  # noqa: BLE001
            return {"total": 0, "mapped": 0, "divided": 0, "not_found": 0}
        return {
            "total": int(total),
            "mapped": int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM ward_address_mappings "
                    "WHERE match_status = 'MAPPED'"
                ).fetchone()["c"]
            ),
            "divided": int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM ward_address_mappings "
                    "WHERE match_status = 'MAPPED_DIVIDED'"
                ).fetchone()["c"]
            ),
            "not_found": int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM ward_address_mappings "
                    "WHERE match_status = 'NOT_FOUND'"
                ).fetchone()["c"]
            ),
        }


def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def lookup_old_to_new(
    *,
    portal_ward_value: str = "",
    old_ward_code: str = "",
    prefer_default: bool = True,
) -> list[dict[str, Any]]:
    """
    Portal/old → new admin options.
    Prefer is_default_new_ward=1 when prefer_default and multiple (divided).
    """
    portal_ward_value = (portal_ward_value or "").strip()
    old_ward_code = (old_ward_code or "").strip()
    if not portal_ward_value and not old_ward_code:
        return []

    clauses: list[str] = ["match_status IN ('MAPPED', 'MAPPED_DIVIDED')"]
    params: list[str] = []
    if portal_ward_value:
        clauses.append("portal_ward_value = ?")
        params.append(portal_ward_value)
    if old_ward_code:
        clauses.append("old_ward_code = ?")
        params.append(old_ward_code)

    sql = f"""
        SELECT *
        FROM ward_address_mappings
        WHERE {' AND '.join(clauses)}
        ORDER BY is_default_new_ward DESC, id ASC
    """
    with get_conn() as conn:
        rows = _rows_to_dicts(conn.execute(sql, params).fetchall())
    if prefer_default and rows:
        defaults = [r for r in rows if int(r.get("is_default_new_ward") or 0) == 1]
        if defaults:
            return defaults
    return rows


def lookup_new_to_old(
    *,
    new_ward_code: str = "",
    new_ward: str = "",
    new_province: str = "",
    prefer_default: bool = True,
) -> list[dict[str, Any]]:
    """
    New admin → portal/old options (để submit portal).
    Match by new_ward_code, or new_ward (+ optional new_province).

    Tên xã/tỉnh so khớp linh hoạt: «Mỹ hạnh» ≈ «Xã Mỹ Hạnh»,
    «Tây Ninh» ≈ «Tỉnh Tây Ninh» (bỏ dấu / tiền tố).
    """
    new_ward_code = (new_ward_code or "").strip()
    new_ward = (new_ward or "").strip()
    new_province = (new_province or "").strip()
    if not new_ward_code and not new_ward:
        return []

    clauses: list[str] = ["match_status IN ('MAPPED', 'MAPPED_DIVIDED')"]
    params: list[str] = []
    if new_ward_code:
        clauses.append("new_ward_code = ?")
        params.append(new_ward_code)
    else:
        # exact trước (nhanh), fallback fuzzy bên dưới
        clauses.append("new_ward = ?")
        params.append(new_ward)
        if new_province:
            clauses.append("new_province = ?")
            params.append(new_province)

    sql = f"""
        SELECT *
        FROM ward_address_mappings
        WHERE {' AND '.join(clauses)}
        ORDER BY is_default_new_ward DESC, id ASC
    """
    with get_conn() as conn:
        rows = _rows_to_dicts(conn.execute(sql, params).fetchall())

        if not rows and not new_ward_code and new_ward:
            ward_key = _place_key(new_ward)
            prov_key = _place_key(new_province) if new_province else ""
            candidates = _rows_to_dicts(
                conn.execute(
                    """
                    SELECT *
                    FROM ward_address_mappings
                    WHERE match_status IN ('MAPPED', 'MAPPED_DIVIDED')
                    ORDER BY is_default_new_ward DESC, id ASC
                    """
                ).fetchall()
            )
            matched: list[dict[str, Any]] = []
            matched_any_prov: list[dict[str, Any]] = []
            for r in candidates:
                if _place_key(str(r.get("new_ward") or "")) != ward_key:
                    continue
                matched_any_prov.append(r)
                if not prov_key or _place_key(str(r.get("new_province") or "")) == prov_key:
                    matched.append(r)
            rows = matched if matched else matched_any_prov

    if prefer_default and rows:
        defaults = [r for r in rows if int(r.get("is_default_new_ward") or 0) == 1]
        if defaults:
            return defaults
    return rows
