"""Location lookups for cascading province → city (district) → ward."""
from __future__ import annotations

from typing import Any

from app.db import get_conn


def list_provinces() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT code, name, inserted_value
            FROM provinces
            ORDER BY name
            """
        ).fetchall()
    return [dict(r) for r in rows]


def list_districts(province_code: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, province_code, name, inserted_value
            FROM districts
            WHERE province_code = ?
            ORDER BY name
            """,
            (province_code,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_wards(district_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, district_id, name, inserted_value
            FROM wards
            WHERE district_id = ?
            ORDER BY name
            """,
            (district_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def province_option_value(row: dict[str, Any]) -> str:
    return str(row.get("inserted_value") or "")


def district_option_value(row: dict[str, Any]) -> str:
    """Portal needs id|name; DB may store only id in inserted_value."""
    raw = str(row.get("inserted_value") or "").strip()
    name = str(row.get("name") or "").strip()
    if "|" in raw:
        return raw
    if raw and name:
        return f"{raw}|{name}"
    return raw or name


def ward_option_value(row: dict[str, Any]) -> str:
    raw = str(row.get("inserted_value") or "").strip()
    name = str(row.get("name") or "").strip()
    if "|" in raw:
        return raw
    if raw and name:
        return f"{raw}|{name}"
    return raw or name


def province_code_from_value(value: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    code = text.split("|", 1)[0].strip()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT code FROM provinces
            WHERE inserted_value = ? OR code = ? OR name = ?
            LIMIT 1
            """,
            (text, code, text),
        ).fetchone()
    return row["code"] if row else None


def district_id_from_value(value: str, province_code: str | None = None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    raw_id = text.split("|", 1)[0].strip()
    name = text.split("|", 1)[1].strip() if "|" in text else text
    with get_conn() as conn:
        if province_code:
            row = conn.execute(
                """
                SELECT id FROM districts
                WHERE province_code = ?
                  AND (
                    inserted_value = ? OR CAST(id AS TEXT) = ?
                    OR name = ? OR inserted_value || '|' || name = ?
                  )
                LIMIT 1
                """,
                (province_code, raw_id, raw_id, name, text),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id FROM districts
                WHERE inserted_value = ? OR CAST(id AS TEXT) = ?
                   OR name = ? OR inserted_value || '|' || name = ?
                LIMIT 1
                """,
                (raw_id, raw_id, name, text),
            ).fetchone()
    return int(row["id"]) if row else None


def resolve_location_fields(row: dict[str, Any]) -> dict[str, str]:
    """Normalize province/district/ward to portal inserted_value (CODE|Name)."""
    prov_in = str(row.get("AddrTmpProvince") or "").strip()
    dist_in = str(row.get("AddrTmpDistrict") or "").strip()
    ward_in = str(row.get("AddrTmpWard") or "").strip()

    out = {
        "AddrTmpProvince": prov_in,
        "AddrTmpDistrict": dist_in,
        "AddrTmpWard": ward_in,
    }

    pcode = province_code_from_value(prov_in)
    if pcode:
        with get_conn() as conn:
            prow = conn.execute(
                "SELECT inserted_value FROM provinces WHERE code = ?", (pcode,)
            ).fetchone()
        if prow:
            out["AddrTmpProvince"] = prow["inserted_value"]

    did = district_id_from_value(dist_in, pcode)
    if did is not None:
        with get_conn() as conn:
            drow = conn.execute(
                "SELECT id, name, inserted_value FROM districts WHERE id = ?",
                (did,),
            ).fetchone()
        if drow:
            out["AddrTmpDistrict"] = district_option_value(dict(drow))

    if did is not None and ward_in:
        raw_id = ward_in.split("|", 1)[0].strip()
        wname = ward_in.split("|", 1)[1].strip() if "|" in ward_in else ward_in
        with get_conn() as conn:
            wrow = conn.execute(
                """
                SELECT id, name, inserted_value FROM wards
                WHERE district_id = ?
                  AND (
                    inserted_value = ? OR CAST(id AS TEXT) = ?
                    OR name = ? OR inserted_value || '|' || name = ?
                  )
                LIMIT 1
                """,
                (did, raw_id, raw_id, wname, ward_in),
            ).fetchone()
        if wrow:
            out["AddrTmpWard"] = ward_option_value(dict(wrow))

    return out
