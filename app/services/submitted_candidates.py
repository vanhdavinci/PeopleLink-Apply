"""Persist successful apply submissions (name + phone + project) beyond batch lifetime."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import get_conn


def normalize_mobile(raw: str) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_submission(
    *,
    project_id: int,
    full_name: str,
    mobile: str,
    submitted_at: str | None = None,
) -> None:
    name = (full_name or "").strip() or "(không tên)"
    phone = normalize_mobile(mobile)
    if not phone:
        return
    when = submitted_at or _now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO submitted_candidates (project_id, full_name, mobile, submitted_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, mobile) DO UPDATE SET
                full_name = excluded.full_name,
                submitted_at = excluded.submitted_at
            """,
            (int(project_id), name, phone, when),
        )


def is_mobile_submitted(mobile: str, *, project_id: int | None = None) -> bool:
    phone = normalize_mobile(mobile)
    if not phone:
        return False
    with get_conn() as conn:
        if project_id is not None:
            row = conn.execute(
                """
                SELECT 1 FROM submitted_candidates
                WHERE project_id = ? AND mobile = ?
                LIMIT 1
                """,
                (int(project_id), phone),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT 1 FROM submitted_candidates
                WHERE mobile = ?
                LIMIT 1
                """,
                (phone,),
            ).fetchone()
    return row is not None


def submitted_lookup_map(mobiles: list[str]) -> dict[str, list[dict[str, Any]]]:
    """mobile_norm → list of {project_id, full_name, submitted_at}."""
    phones = sorted({normalize_mobile(m) for m in mobiles if normalize_mobile(m)})
    if not phones:
        return {}
    placeholders = ",".join("?" * len(phones))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT project_id, full_name, mobile, submitted_at
            FROM submitted_candidates
            WHERE mobile IN ({placeholders})
            """,
            phones,
        ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = str(r["mobile"])
        out.setdefault(key, []).append(dict(r))
    return out


def list_submitted_for_project(project_id: int) -> list[dict[str, Any]]:
    """Ứng viên đã submit thành công cho 1 project (tên + SĐT)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, full_name, mobile, submitted_at
            FROM submitted_candidates
            WHERE project_id = ?
            ORDER BY submitted_at DESC, id DESC
            """,
            (int(project_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def annotate_rows_submitted(rows: list[dict]) -> list[dict]:
    """Thêm cột Submitted (✓ / —) dựa trên SĐT đã đẩy thành công trước đó."""
    mobiles = [str(r.get("Mobile") or "") for r in rows]
    lookup = submitted_lookup_map(mobiles)
    out: list[dict] = []
    for r in rows:
        item = dict(r)
        phone = normalize_mobile(str(item.get("Mobile") or ""))
        hits = lookup.get(phone) or []
        if hits:
            item["Submitted"] = "✓"
            pids = ", ".join(str(h["project_id"]) for h in hits[:3])
            if len(hits) > 3:
                pids += "…"
            item["SubmittedNote"] = f"Đã submit project: {pids}"
        else:
            item["Submitted"] = "—"
            item["SubmittedNote"] = ""
        out.append(item)
    return out
