"""App user (single operator) helpers + project membership link."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import get_conn

APP_USER_FULL_NAME = "Bùi Thị Kim Ngân"
APP_USER_FIRST_NAME = "Kim Ngaan"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_app_user() -> dict[str, Any]:
    """Ensure the singleton app user row exists; return it."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE full_name = ?", (APP_USER_FULL_NAME,)
        ).fetchone()
        if row:
            return dict(row)
        conn.execute(
            """
            INSERT INTO users (full_name, first_name, updated_at)
            VALUES (?, ?, ?)
            """,
            (APP_USER_FULL_NAME, APP_USER_FIRST_NAME, _now()),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE full_name = ?", (APP_USER_FULL_NAME,)
        ).fetchone()
        assert row is not None
        return dict(row)


def get_app_user() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE full_name = ?", (APP_USER_FULL_NAME,)
        ).fetchone()
    return dict(row) if row else None


def update_app_user_fields(
    *,
    recruiter_pic: str | None = None,
    headcount_request_id: str | None = None,
) -> dict[str, Any]:
    """Fill RecruiterPIC / HeadcountRequestID for the app user."""
    user = ensure_app_user()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET recruiter_pic = ?,
                headcount_request_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                (recruiter_pic or "").strip() or None,
                (headcount_request_id or "").strip() or None,
                _now(),
                user["id"],
            ),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    assert row is not None
    return dict(row)


def link_members_to_app_user(conn=None) -> int:
    """Set project_members.user_id where full_name matches the app user."""
    user = ensure_app_user()

    def _run(c) -> int:
        cur = c.execute(
            """
            UPDATE project_members
            SET user_id = ?
            WHERE full_name = ?
              AND IFNULL(user_id, -1) != ?
            """,
            (user["id"], APP_USER_FULL_NAME, user["id"]),
        )
        # Clear stale links if name no longer matches (safety)
        c.execute(
            """
            UPDATE project_members
            SET user_id = NULL
            WHERE user_id = ? AND full_name != ?
            """,
            (user["id"], APP_USER_FULL_NAME),
        )
        return cur.rowcount

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def list_user_projects(user_id: int | None = None) -> list[dict[str, Any]]:
    """Projects where this user appears in Members (for later list UI)."""
    user = ensure_app_user() if user_id is None else None
    uid = user_id if user_id is not None else user["id"]
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                p.project_id,
                p.project_code,
                p.project_name,
                p.start_date,
                p.end_date,
                p.is_expired,
                p.total_percent_target,
                pm.full_name AS member_full_name
            FROM project_members pm
            JOIN projects p ON p.project_id = pm.project_id
            WHERE pm.user_id = ?
            ORDER BY (p.end_date IS NULL), p.end_date DESC, p.project_id DESC
            """,
            (uid,),
        ).fetchall()
    return [dict(r) for r in rows]
