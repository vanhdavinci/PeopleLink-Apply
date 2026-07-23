"""Sync districts (city) + wards from PeopleLink location API into SQLite."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import LOCATION_AUTH, URL_LIST_DISTRICT, URL_LIST_WARD
from app.db import get_conn

# Mã province lỗi: API Area không trả district/ward (vd. Quy Nhơn không phải tỉnh).
BAD_PROVINCE_CODES: frozenset[str] = frozenset({"QUYNHON"})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def purge_bad_provinces() -> list[str]:
    """
    Xóa province mã sai + mã số (01/79…) khỏi DB.

    Sync location chỉ dùng mã chữ (ANGIANG, HANOI, …). Mã số trùng tên tỉnh
    nhưng không có district/ward trong DB → dropdown trống / sync lặp vô ích.
    """
    removed: list[str] = []
    with get_conn() as conn:
        if BAD_PROVINCE_CODES:
            placeholders = ",".join("?" for _ in BAD_PROVINCE_CODES)
            rows = conn.execute(
                f"""
                SELECT code FROM provinces
                WHERE code IN ({placeholders}) OR code GLOB '[0-9]*'
                ORDER BY code
                """,
                tuple(sorted(BAD_PROVINCE_CODES)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT code FROM provinces
                WHERE code GLOB '[0-9]*'
                ORDER BY code
                """
            ).fetchall()
        codes = [r["code"] for r in rows]
        for code in codes:
            conn.execute("DELETE FROM provinces WHERE code = ?", (code,))
            removed.append(code)
    return removed


def _options(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (value, text) pairs, skipping empty placeholder options."""
    data = payload.get("Data") or []
    out: list[tuple[str, str]] = []
    for item in data:
        value = str(item.get("Value") or "").strip()
        text = str(item.get("Text") or "").strip()
        if not value:
            continue
        out.append((value, text))
    return out


@dataclass
class SyncResult:
    province_count: int = 0
    district_count: int = 0
    ward_count: int = 0
    errors: list[str] = field(default_factory=list)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=60.0,
        headers={
            "Authorization": LOCATION_AUTH,
            "Accept": "application/json",
        },
        verify=False,  # api_adhoc.plsvn.com cert hostname mismatch
    )


def fetch_districts(client: httpx.Client, province_code: str) -> list[tuple[int, str, str]]:
    """Area = province.code → list of (district_id, name, inserted_value)."""
    r = client.get(
        URL_LIST_DISTRICT,
        params={"text_df": "", "value_df": "", "Area": province_code},
    )
    r.raise_for_status()
    payload = r.json()
    if str(payload.get("Status", "")).lower() != "success" and payload.get("Code") not in (200, "200"):
        raise RuntimeError(f"List_District Area={province_code}: {payload}")

    rows: list[tuple[int, str, str]] = []
    for value, text in _options(payload):
        rows.append((int(value), text, value))
    return rows


def fetch_wards(client: httpx.Client, district_id: int) -> list[tuple[int, str, str]]:
    """ID_District = districts.id → list of (ward_id, name, inserted_value)."""
    r = client.get(
        URL_LIST_WARD,
        params={"text_df": "", "value_df": "", "ID_District": str(district_id)},
    )
    r.raise_for_status()
    payload = r.json()
    if str(payload.get("Status", "")).lower() != "success" and payload.get("Code") not in (200, "200"):
        raise RuntimeError(f"List_Ward ID_District={district_id}: {payload}")

    rows: list[tuple[int, str, str]] = []
    for value, text in _options(payload):
        rows.append((int(value), text, value))
    return rows


def sync_locations(
    *,
    province_codes: list[str] | None = None,
    letter_codes_only: bool = True,
    sync_wards: bool = True,
    purge_bad: bool = True,
    progress: Callable[[str], None] | None = None,
) -> SyncResult:
    """
    Loop provinces → districts (Area=province.code) → wards (ID_District=district.id).

    letter_codes_only: API Area expects codes like ANGIANG (not numeric 01/79).
    purge_bad: xóa mã sai / mã số trước khi sync (tránh lặp vô ích).
    """
    result = SyncResult()
    started = _now()

    if purge_bad:
        removed = purge_bad_provinces()
        if progress and removed:
            progress(f"purged bad provinces: {', '.join(removed)}")

    with get_conn() as conn:
        if province_codes is None:
            if letter_codes_only:
                sql = (
                    "SELECT code, name FROM provinces "
                    "WHERE code GLOB '[A-Z]*' ORDER BY code"
                )
            else:
                sql = "SELECT code, name FROM provinces ORDER BY code"
            provinces = list(conn.execute(sql))
        else:
            provinces = [
                conn.execute(
                    "SELECT code, name FROM provinces WHERE code = ?", (code,)
                ).fetchone()
                for code in province_codes
            ]
            provinces = [p for p in provinces if p]

        # Bỏ mã đã biết là trống / sai — không gọi API
        provinces = [
            p for p in provinces if str(p["code"]) not in BAD_PROVINCE_CODES
        ]

        run_id = conn.execute(
            """
            INSERT INTO sync_runs (kind, started_at, status)
            VALUES ('location', ?, 'running')
            """,
            (started,),
        ).lastrowid

        # Clear children first (wards → districts) then refill
        conn.execute("DELETE FROM wards")
        conn.execute("DELETE FROM districts")

    try:
        with _client() as client:
            for prov in provinces:
                pcode = prov["code"]
                if progress:
                    progress(f"province {pcode}")

                try:
                    districts = fetch_districts(client, pcode)
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"{pcode}: {exc}")
                    continue

                if not districts:
                    result.errors.append(f"{pcode}: no districts (skipped)")
                    continue

                result.province_count += 1
                synced_at = _now()

                with get_conn() as conn:
                    for district_id, name, inserted_value in districts:
                        conn.execute(
                            """
                            INSERT INTO districts (id, province_code, name, inserted_value, synced_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                province_code = excluded.province_code,
                                name = excluded.name,
                                inserted_value = excluded.inserted_value,
                                synced_at = excluded.synced_at
                            """,
                            (district_id, pcode, name, inserted_value, synced_at),
                        )
                        result.district_count += 1

                        if not sync_wards:
                            continue

                        if progress:
                            progress(f"  ward district={district_id}")

                        try:
                            wards = fetch_wards(client, district_id)
                        except Exception as exc:  # noqa: BLE001
                            result.errors.append(f"district {district_id}: {exc}")
                            continue

                        for ward_id, wname, wvalue in wards:
                            conn.execute(
                                """
                                INSERT INTO wards (id, district_id, name, inserted_value, synced_at)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(id) DO UPDATE SET
                                    district_id = excluded.district_id,
                                    name = excluded.name,
                                    inserted_value = excluded.inserted_value,
                                    synced_at = excluded.synced_at
                                """,
                                (ward_id, district_id, wname, wvalue, synced_at),
                            )
                            result.ward_count += 1

        status = "success" if not result.errors else "success_with_errors"
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?,
                    province_count = ?, district_count = ?, ward_count = ?,
                    error = ?
                WHERE id = ?
                """,
                (
                    _now(),
                    status,
                    result.province_count,
                    result.district_count,
                    result.ward_count,
                    "\n".join(result.errors[:50]) if result.errors else None,
                    run_id,
                ),
            )
    except Exception as exc:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = 'failed', error = ?
                WHERE id = ?
                """,
                (_now(), str(exc), run_id),
            )
        raise

    return result
