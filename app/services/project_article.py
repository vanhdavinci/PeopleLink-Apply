"""Bài viết + ảnh đính kèm theo project (HTML giữ format)."""
from __future__ import annotations

import base64
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.db import get_conn

ARTICLE_UPLOAD_ROOT = DATA_DIR / "uploads" / "project_articles"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def article_dir(project_id: int) -> Path:
    path = ARTICLE_UPLOAD_ROOT / str(int(project_id))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_article(project_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT project_id, article_html, article_updated_at
            FROM projects WHERE project_id = ?
            """,
            (int(project_id),),
        ).fetchone()
    if row is None:
        return {
            "project_id": int(project_id),
            "article_html": "",
            "article_updated_at": "",
        }
    return {
        "project_id": int(row["project_id"]),
        "article_html": row["article_html"] or "",
        "article_updated_at": row["article_updated_at"] or "",
    }


def save_article(project_id: int, html: str) -> dict[str, Any]:
    body = html or ""
    when = _now()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE projects
            SET article_html = ?, article_updated_at = ?
            WHERE project_id = ?
            """,
            (body, when, int(project_id)),
        )
    return get_article(int(project_id))


def list_article_images(project_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, rel_path, original_name, uploaded_at
            FROM project_article_images
            WHERE project_id = ?
            ORDER BY id ASC
            """,
            (int(project_id),),
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        abs_path = DATA_DIR / item["rel_path"]
        item["abs_path"] = str(abs_path)
        item["exists"] = abs_path.is_file()
        out.append(item)
    return out


def add_article_image(
    project_id: int,
    *,
    file_bytes: bytes,
    original_name: str,
) -> dict[str, Any]:
    safe = re.sub(r"[^\w.\-]+", "_", (original_name or "image").strip()) or "image"
    if len(safe) > 80:
        safe = safe[-80:]
    filename = f"{uuid.uuid4().hex[:12]}_{safe}"
    folder = article_dir(project_id)
    abs_path = folder / filename
    abs_path.write_bytes(file_bytes)
    rel = str(Path("uploads") / "project_articles" / str(int(project_id)) / filename)
    # Normalize separators for DB
    rel = rel.replace("\\", "/")
    when = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO project_article_images
                (project_id, rel_path, original_name, uploaded_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(project_id), rel, original_name or safe, when),
        )
        image_id = int(cur.lastrowid)
    return {
        "id": image_id,
        "project_id": int(project_id),
        "rel_path": rel,
        "original_name": original_name or safe,
        "uploaded_at": when,
        "abs_path": str(abs_path),
        "exists": True,
    }


def delete_article_image(image_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT rel_path FROM project_article_images WHERE id = ?",
            (int(image_id),),
        ).fetchone()
        if row is None:
            return
        conn.execute(
            "DELETE FROM project_article_images WHERE id = ?", (int(image_id),)
        )
    path = DATA_DIR / str(row["rel_path"])
    if path.is_file():
        path.unlink(missing_ok=True)


def image_data_uri(abs_path: str | Path) -> str | None:
    path = Path(abs_path)
    if not path.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def html_to_plain(html: str) -> str:
    """Strip tags roughly for clipboard plain text."""
    text = html or ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
