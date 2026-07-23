"""Sync portal projects + members into SQLite; mark expired by EndDate."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.config import PORTAL_BASE, URL_PROJECT_LIST, URL_SEARCH_PROJECTS
from app.db import get_conn, set_setting

SETTING_PORTAL_COOKIE = "portal_cookie"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_portal_date(value: str | None) -> str | None:
    """Convert DD/MM/YYYY (API) → YYYY-MM-DD. Pass through if already ISO."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


@dataclass
class ProjectSyncResult:
    project_count: int = 0
    member_count: int = 0
    expired_count: int = 0
    unexpired_count: int = 0
    errors: list[str] = field(default_factory=list)


def resolve_portal_cookie(cookie: str | None = None) -> str | None:
    """Use the cookie passed from UI/CLI for this sync call only.

    Env PEOPLELINK_PORTAL_COOKIE is a fallback for CLI/scripts.
    Settings persistence is optional via save_portal_cookie() — UI does not auto-save.
    """
    if cookie and cookie.strip():
        return cookie.strip()
    env = os.getenv("PEOPLELINK_PORTAL_COOKIE", "").strip()
    return env or None


def save_portal_cookie(cookie: str) -> None:
    set_setting(SETTING_PORTAL_COOKIE, cookie.strip())


def _extract_project_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("Data", "data", "Result", "result", "Items", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    if "ProjectID" in payload or "project_id" in payload:
        return [payload]
    return []


def fetch_projects_from_api(
    cookie: str,
    *,
    keyword: str = "",
) -> list[dict[str, Any]]:
    """
    Call Search_ProjectHeadcount exactly like Postman/portal List page JS:
      POST application/x-www-form-urlencoded  body: keyword=
    Cookie is required per call (entered in UI each sync).
    """
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
        "referer": URL_PROJECT_LIST,
        "origin": PORTAL_BASE,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
        "Cookie": cookie,
    }
    # Match Postman raw body "keyword=" (empty keyword = all projects)
    body = f"keyword={keyword}"

    with httpx.Client(
        timeout=60.0, verify=False, follow_redirects=True, headers=headers
    ) as client:
        response = client.post(URL_SEARCH_PROJECTS, content=body)

        ctype = (response.headers.get("content-type") or "").lower()
        if response.status_code in (401, 403) or (
            "html" in ctype and "json" not in ctype and not response.text.strip().startswith(("[", "{"))
        ):
            raise RuntimeError(
                "Portal trả HTML/unauthorized (cookie hết hạn hoặc sai). "
                "Dán lại ASP.NET_SessionId rồi sync."
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Không parse được JSON từ Search_ProjectHeadcount "
                f"(status={response.status_code}, body[:200]={response.text[:200]!r})"
            ) from exc

    items = _extract_project_list(payload)
    if not items:
        raise RuntimeError("API project không trả danh sách (rỗng hoặc format lạ).")
    return items

def upsert_projects(
    items: list[dict[str, Any]],
    *,
    synced_at: str | None = None,
) -> ProjectSyncResult:
    """Save/update projects + members from API-shaped dicts (no HTTP)."""
    result = ProjectSyncResult()
    synced_at = synced_at or _now()

    with get_conn() as conn:
        for raw in items:
            try:
                project_id = raw.get("ProjectID", raw.get("project_id"))
                project_id = int(project_id)
            except (TypeError, ValueError):
                result.errors.append(f"missing ProjectID: {raw!r:.200}")
                continue

            name = (
                raw.get("ProjectName")
                or raw.get("project_name")
                or f"Project {project_id}"
            )
            start_raw = raw.get("StartDate") or raw.get("start_date")
            end_raw = raw.get("EndDate") or raw.get("end_date")
            start_iso = parse_portal_date(
                str(start_raw) if start_raw is not None else None
            )
            end_iso = parse_portal_date(str(end_raw) if end_raw is not None else None)

            conn.execute(
                """
                INSERT INTO projects (
                    project_id, project_code, project_name,
                    start_date, end_date, start_date_raw, end_date_raw,
                    project_type, master_finished_person, master_total_person,
                    total_percent_target, raw_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    project_code = excluded.project_code,
                    project_name = excluded.project_name,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    start_date_raw = excluded.start_date_raw,
                    end_date_raw = excluded.end_date_raw,
                    project_type = excluded.project_type,
                    master_finished_person = excluded.master_finished_person,
                    master_total_person = excluded.master_total_person,
                    total_percent_target = excluded.total_percent_target,
                    raw_json = excluded.raw_json,
                    synced_at = excluded.synced_at
                """,
                (
                    project_id,
                    raw.get("ProjectCode") or raw.get("project_code"),
                    str(name),
                    start_iso,
                    end_iso,
                    str(start_raw) if start_raw is not None else None,
                    str(end_raw) if end_raw is not None else None,
                    raw.get("ProjectType", raw.get("project_type")),
                    raw.get("MasterFinishedPerson", raw.get("master_finished_person")),
                    raw.get("MasterTotalPerson", raw.get("master_total_person")),
                    raw.get("TotalPercentTarget", raw.get("total_percent_target")),
                    json.dumps(raw, ensure_ascii=False),
                    synced_at,
                ),
            )
            result.project_count += 1

            members = raw.get("Members") or raw.get("members") or []
            conn.execute(
                "DELETE FROM project_members WHERE project_id = ?", (project_id,)
            )
            if not isinstance(members, list):
                continue

            # Lazy import to avoid circular deps at module load
            from app.services.user_service import APP_USER_FULL_NAME, ensure_app_user

            app_user_id = ensure_app_user()["id"]

            for member in members:
                if not isinstance(member, dict):
                    continue
                full_name = (
                    member.get("Member_FullName")
                    or member.get("full_name")
                    or member.get("FullName")
                    or ""
                ).strip()
                if not full_name:
                    continue
                first_name = (
                    member.get("Member_FirstName")
                    or member.get("first_name")
                    or member.get("FirstName")
                )
                member_user_id = (
                    app_user_id if full_name == APP_USER_FULL_NAME else None
                )
                conn.execute(
                    """
                    INSERT INTO project_members (
                        project_id, user_id, first_name, full_name, synced_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, full_name) DO UPDATE SET
                        user_id = excluded.user_id,
                        first_name = excluded.first_name,
                        synced_at = excluded.synced_at
                    """,
                    (
                        project_id,
                        member_user_id,
                        str(first_name).strip() if first_name else None,
                        full_name,
                        synced_at,
                    ),
                )
                result.member_count += 1

    from app.services.user_service import link_members_to_app_user

    link_members_to_app_user()
    return result


def mark_expired_projects(*, as_of: date | None = None) -> ProjectSyncResult:
    """
    Flag projects whose end_date < as_of as expired.
    Also clear flag if end_date was extended past as_of.
    """
    result = ProjectSyncResult()
    day = (as_of or date.today()).isoformat()
    marked_at = _now()

    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE projects
            SET is_expired = 1, expired_marked_at = ?
            WHERE end_date IS NOT NULL
              AND end_date < ?
              AND IFNULL(is_expired, 0) = 0
            """,
            (marked_at, day),
        )
        result.expired_count = cur.rowcount

        cur = conn.execute(
            """
            UPDATE projects
            SET is_expired = 0, expired_marked_at = NULL
            WHERE IFNULL(is_expired, 0) = 1
              AND end_date IS NOT NULL
              AND end_date >= ?
            """,
            (day,),
        )
        result.unexpired_count = cur.rowcount

        result.project_count = conn.execute(
            "SELECT COUNT(*) AS c FROM projects WHERE IFNULL(is_expired, 0) = 1"
        ).fetchone()["c"]

    return result


def sync_projects(
    *,
    cookie: str | None = None,
    items: list[dict[str, Any]] | None = None,
    keyword: str = "",
    save_cookie: bool = False,
    progress: Callable[[str], None] | None = None,
) -> ProjectSyncResult:
    """
    Button-ready entrypoint: fetch (or use provided items) → upsert → mark expired.

    Usage from Streamlit:
        result = sync_projects(cookie=cookie_input)  # paste cookie each time
    """
    started = _now()
    result = ProjectSyncResult()

    with get_conn() as conn:
        run_id = conn.execute(
            """
            INSERT INTO sync_runs (kind, started_at, status)
            VALUES ('projects', ?, 'running')
            """,
            (started,),
        ).lastrowid

    try:
        if items is None:
            resolved = resolve_portal_cookie(cookie)
            if not resolved:
                raise RuntimeError(
                    "Chưa có portal cookie. Dán cookie mỗi lần sync "
                    "(hoặc set PEOPLELINK_PORTAL_COOKIE cho CLI)."
                )
            if save_cookie:
                save_portal_cookie(resolved)
            if progress:
                progress("Fetching projects from portal...")
            items = fetch_projects_from_api(resolved, keyword=keyword)
        if progress:
            progress(f"Upserting {len(items)} projects...")
        upsert_result = upsert_projects(items)
        result.project_count = upsert_result.project_count
        result.member_count = upsert_result.member_count
        result.errors.extend(upsert_result.errors)

        if progress:
            progress("Marking expired projects...")
        expired_result = mark_expired_projects()
        result.expired_count = expired_result.expired_count
        result.unexpired_count = expired_result.unexpired_count

        status = "success" if not result.errors else "success_with_errors"
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?,
                    project_count = ?, member_count = ?, expired_count = ?,
                    error = ?
                WHERE id = ?
                """,
                (
                    _now(),
                    status,
                    result.project_count,
                    result.member_count,
                    result.expired_count,
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
