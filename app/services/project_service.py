"""Project helpers: detail, link_apply, members for Projects tab."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import get_conn
from app.services.user_service import ensure_app_user


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_project(project_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", (int(project_id),)
        ).fetchone()
    return dict(row) if row else None


def list_project_members(project_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, user_id, first_name, full_name, synced_at
            FROM project_members
            WHERE project_id = ?
            ORDER BY full_name COLLATE NOCASE
            """,
            (int(project_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def update_project_link_apply(project_id: int, link_apply: str) -> dict[str, Any]:
    link = (link_apply or "").strip()
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET link_apply = ? WHERE project_id = ?",
            (link or None, int(project_id)),
        )
    project = get_project(int(project_id))
    if project is None:
        raise ValueError(f"Không thấy project #{project_id}")
    return project


def list_projects_for_user(*, include_expired: bool = True) -> list[dict[str, Any]]:
    """Projects gắn app user — đủ field cho thẻ + link_apply."""
    user = ensure_app_user()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                p.project_id,
                p.project_code,
                p.project_name,
                p.start_date,
                p.end_date,
                p.start_date_raw,
                p.end_date_raw,
                p.project_type,
                p.master_finished_person,
                p.master_total_person,
                p.total_percent_target,
                p.is_expired,
                p.link_apply,
                p.synced_at
            FROM project_members pm
            JOIN projects p ON p.project_id = pm.project_id
            WHERE pm.user_id = ?
            ORDER BY
                CASE WHEN IFNULL(p.is_expired, 0) = 0 THEN 0 ELSE 1 END,
                (p.end_date IS NULL),
                p.end_date DESC,
                p.project_id DESC
            """,
            (user["id"],),
        ).fetchall()
    out = [dict(r) for r in rows]
    if not include_expired:
        out = [p for p in out if not int(p.get("is_expired") or 0)]
    return out


def project_type_label(project_type: Any) -> str:
    try:
        t = int(project_type)
    except (TypeError, ValueError):
        return "—"
    if t == 3:
        return "Adhoc"
    return str(t)


def format_display_date(iso_or_raw: str | None, raw: str | None = None) -> str:
    text = (raw or "").strip()
    if text:
        return text
    iso = (iso_or_raw or "").strip()
    if not iso:
        return "—"
    try:
        y, m, d = iso[:10].split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return iso
