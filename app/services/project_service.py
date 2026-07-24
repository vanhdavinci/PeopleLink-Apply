"""Project helpers: detail, link_apply, members for Projects tab."""
from __future__ import annotations

import base64
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import ROOT_DIR
from app.db import get_conn
from app.services.user_service import ensure_app_user

PICTURES_DIR = ROOT_DIR / "pictures"
_DEFAULT_LOGO_NAMES = ("PeopleLink.png", "peoplelink.png", "Peoplelink.png")
_SKIP_STEMS = {"avatar", "background"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fold_key(text: str) -> str:
    raw = unicodedata.normalize("NFD", (text or "").strip())
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    raw = raw.casefold()
    raw = re.sub(r"[^a-z0-9]+", "", raw)
    return raw


@lru_cache(maxsize=1)
def _logo_candidates() -> list[tuple[str, Path]]:
    """(match_key, path) sorted longest key first."""
    if not PICTURES_DIR.is_dir():
        return []
    items: list[tuple[str, Path]] = []
    for path in PICTURES_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
            continue
        stem = path.stem
        if stem.casefold() in _SKIP_STEMS:
            continue
        if stem.casefold() in {"peoplelink"}:
            continue  # default only — không match theo tên project
        key = _fold_key(stem)
        if key:
            items.append((key, path))
        # DHG-Bipp → cũng match "dhg", "bipp"
        for part in re.split(r"[-_\s]+", stem):
            part_key = _fold_key(part)
            if part_key and len(part_key) >= 3:
                items.append((part_key, path))
    items.sort(key=lambda x: len(x[0]), reverse=True)
    return items


def default_project_logo_path() -> Path | None:
    for name in _DEFAULT_LOGO_NAMES:
        path = PICTURES_DIR / name
        if path.is_file():
            return path
    # fallback bất kỳ file peoplelink.*
    if PICTURES_DIR.is_dir():
        for path in PICTURES_DIR.iterdir():
            if path.is_file() and path.stem.casefold() == "peoplelink":
                return path
    return None


def resolve_project_logo_path(
    project_name: str = "",
    project_code: str = "",
) -> Path | None:
    """
    Chọn ảnh logo trong pictures/ theo tên/mã dự án.
    Không khớp → PeopleLink.png / peoplelink.png.
    """
    haystack = _fold_key(f"{project_name} {project_code}")
    if haystack:
        for key, path in _logo_candidates():
            if key in haystack:
                return path
    return default_project_logo_path()


def project_logo_data_uri(
    project_name: str = "",
    project_code: str = "",
) -> str | None:
    path = resolve_project_logo_path(project_name, project_code)
    if path is None or not path.is_file():
        return None
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


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


def set_project_bookmarked(project_id: int, bookmarked: bool) -> dict[str, Any]:
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET is_bookmarked = ? WHERE project_id = ?",
            (1 if bookmarked else 0, int(project_id)),
        )
    project = get_project(int(project_id))
    if project is None:
        raise ValueError(f"Không thấy project #{project_id}")
    return project


def toggle_project_bookmark(project_id: int) -> dict[str, Any]:
    project = get_project(int(project_id))
    if project is None:
        raise ValueError(f"Không thấy project #{project_id}")
    now = not bool(int(project.get("is_bookmarked") or 0))
    return set_project_bookmarked(int(project_id), now)


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
                p.is_bookmarked,
                p.synced_at
            FROM project_members pm
            JOIN projects p ON p.project_id = pm.project_id
            WHERE pm.user_id = ?
            ORDER BY
                CASE WHEN IFNULL(p.is_bookmarked, 0) = 1 THEN 0 ELSE 1 END,
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
