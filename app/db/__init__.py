from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import DB_PATH

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Columns added after the first scaffold — applied on existing DBs via ALTER.
_PROJECT_COLUMNS: dict[str, str] = {
    "start_date_raw": "TEXT",
    "end_date_raw": "TEXT",
    "master_finished_person": "INTEGER",
    "master_total_person": "INTEGER",
    "total_percent_target": "INTEGER",
    "is_expired": "INTEGER NOT NULL DEFAULT 0",
    "expired_marked_at": "TEXT",
    "link_apply": "TEXT",
    "article_html": "TEXT",
    "article_updated_at": "TEXT",
    "is_bookmarked": "INTEGER NOT NULL DEFAULT 0",
}

_SYNC_RUN_COLUMNS: dict[str, str] = {
    "project_count": "INTEGER DEFAULT 0",
    "member_count": "INTEGER DEFAULT 0",
    "expired_count": "INTEGER DEFAULT 0",
}


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _add_missing_columns(
    conn: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    existing = _existing_columns(conn, table)
    for name, decl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Idempotent upgrades for DBs created before newer columns/tables."""
    _add_missing_columns(conn, "projects", _PROJECT_COLUMNS)
    _add_missing_columns(conn, "sync_runs", _SYNC_RUN_COLUMNS)
    _add_missing_columns(
        conn,
        "project_members",
        {"user_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL"},
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_expired ON projects(is_expired)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_members_user ON project_members(user_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS submitted_candidates (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            full_name     TEXT NOT NULL,
            mobile        TEXT NOT NULL,
            submitted_at  TEXT NOT NULL,
            UNIQUE (project_id, mobile)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_submitted_mobile ON submitted_candidates(mobile)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_submitted_project ON submitted_candidates(project_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_article_images (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id     INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            rel_path       TEXT NOT NULL,
            original_name  TEXT,
            uploaded_at    TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_article_images_project "
        "ON project_article_images(project_id)"
    )
    # Unused leftover — never read/written by app code
    conn.execute("DROP TABLE IF EXISTS form_templates")


def init_db(db_path: Path | None = None) -> Path:
    path = Path(db_path) if db_path else DB_PATH
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(path) as conn:
        conn.executescript(sql)
        migrate_schema(conn)
        conn.commit()

    # Seed singleton app user + link existing members (after tables exist)
    from app.services.user_service import ensure_app_user, link_members_to_app_user

    ensure_app_user()
    link_members_to_app_user()
    return path


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def db_stats() -> dict[str, int]:
    tables = (
        "provinces",
        "districts",
        "wards",
        "projects",
        "project_members",
        "users",
        "apply_links",
        "candidates",
        "submitted_candidates",
        "sync_runs",
        "ward_address_mappings",
    )
    with get_conn() as conn:
        stats: dict[str, int] = {}
        for t in tables:
            try:
                stats[t] = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()[
                    "c"
                ]
            except sqlite3.Error:
                stats[t] = 0
        try:
            stats["projects_expired"] = conn.execute(
                "SELECT COUNT(*) AS c FROM projects WHERE IFNULL(is_expired, 0) = 1"
            ).fetchone()["c"]
        except sqlite3.Error:
            stats["projects_expired"] = 0
        return stats
