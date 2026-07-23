-- PeopleLink Apply Tool — local SQLite schema

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Location tree (sync first)
CREATE TABLE IF NOT EXISTS provinces (
    code       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    inserted_value  TEXT NOT NULL UNIQUE,
    synced_at  TEXT
);

CREATE TABLE IF NOT EXISTS districts (
    id            INTEGER PRIMARY KEY,
    province_code TEXT NOT NULL REFERENCES provinces(code) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    inserted_value     TEXT NOT NULL UNIQUE,
    synced_at     TEXT
);

CREATE TABLE IF NOT EXISTS wards (
    id          INTEGER PRIMARY KEY,
    district_id INTEGER NOT NULL REFERENCES districts(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    inserted_value   TEXT NOT NULL UNIQUE,
    synced_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_districts_province ON districts(province_code);
CREATE INDEX IF NOT EXISTS idx_wards_district ON wards(district_id);
CREATE INDEX IF NOT EXISTS idx_provinces_name ON provinces(name);
CREATE INDEX IF NOT EXISTS idx_districts_name ON districts(name);
CREATE INDEX IF NOT EXISTS idx_wards_name ON wards(name);

CREATE TABLE IF NOT EXISTS sync_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,          -- location | projects
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,          -- running | success | failed | success_with_errors
    province_count  INTEGER DEFAULT 0,
    district_count  INTEGER DEFAULT 0,
    ward_count      INTEGER DEFAULT 0,
    project_count   INTEGER DEFAULT 0,
    member_count    INTEGER DEFAULT 0,
    expired_count   INTEGER DEFAULT 0,
    error           TEXT
);

-- Portal projects (optional, needs cookie)
CREATE TABLE IF NOT EXISTS projects (
    project_id              INTEGER PRIMARY KEY,
    project_code            TEXT,
    project_name            TEXT NOT NULL,
    start_date              TEXT,          -- ISO YYYY-MM-DD
    end_date                TEXT,          -- ISO YYYY-MM-DD
    start_date_raw          TEXT,          -- as returned by API (DD/MM/YYYY)
    end_date_raw            TEXT,
    project_type            INTEGER,
    master_finished_person  INTEGER,
    master_total_person     INTEGER,
    total_percent_target    INTEGER,
    is_expired              INTEGER NOT NULL DEFAULT 0,  -- 0 active | 1 expired
    expired_marked_at       TEXT,
    raw_json                TEXT,
    synced_at               TEXT
);

-- Single local operator of this app (fill RecruiterPIC / HeadcountRequestID)
CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name            TEXT NOT NULL UNIQUE,
    first_name           TEXT,
    recruiter_pic        TEXT,   -- RecruiterPIC (portal), fill manually
    headcount_request_id TEXT,   -- HeadcountRequestID, fill manually
    updated_at           TEXT
);

CREATE TABLE IF NOT EXISTS project_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    first_name  TEXT,
    full_name   TEXT NOT NULL,
    synced_at   TEXT,
    UNIQUE (project_id, full_name)
);

CREATE INDEX IF NOT EXISTS idx_projects_code ON projects(project_code);
CREATE INDEX IF NOT EXISTS idx_projects_end_date ON projects(end_date);
CREATE INDEX IF NOT EXISTS idx_members_project ON project_members(project_id);

CREATE TABLE IF NOT EXISTS apply_links (
    recruiter_id INTEGER PRIMARY KEY,      -- HeadcountReqRecruiterID
    project_id   INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    position     TEXT,
    recruiter    TEXT,
    apply_url    TEXT NOT NULL,
    synced_at    TEXT
);

CREATE TABLE IF NOT EXISTS form_templates (
    recruiter_id INTEGER PRIMARY KEY,
    hidden_json  TEXT NOT NULL,
    fetched_at   TEXT NOT NULL
);

-- Import / submit jobs
CREATE TABLE IF NOT EXISTS import_batches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    project_id    INTEGER,
    recruiter_id  INTEGER,
    created_at    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft'  -- draft | running | done
);

CREATE TABLE IF NOT EXISTS candidates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    row_no        INTEGER NOT NULL,
    full_name     TEXT,
    mobile        TEXT,
    email         TEXT,
    payload_json  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | invalid | success | failed
    error         TEXT,
    response_body TEXT,
    submitted_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_candidates_batch ON candidates(batch_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);

-- Ward address mapping (portal/old admin ↔ new 2-level admin after 01/07/2025)
-- Source CSV: ward_mapping_old_to_new.csv
-- Portal submit uses OLD (province+district+ward). Batch data may use NEW.
CREATE TABLE IF NOT EXISTS ward_address_mappings (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    portal_ward_name     TEXT,              -- CSV name (portal ward list)
    portal_ward_value    TEXT,              -- CSV inserted_value (= wards.id / portal id)
    name_normalized      TEXT,
    match_status         TEXT,              -- MAPPED | MAPPED_DIVIDED | NOT_FOUND
    mapping_type         TEXT,              -- merged | divided | unchanged | renamed
    is_default_new_ward  INTEGER NOT NULL DEFAULT 0,  -- 1 = default when old→new divided
    old_ward             TEXT,
    old_district         TEXT,
    old_province         TEXT,
    old_ward_code        TEXT,
    old_district_code    TEXT,
    old_province_code    TEXT,
    old_full_address     TEXT,
    new_ward             TEXT,
    new_province         TEXT,
    new_ward_code        TEXT,
    new_province_code    TEXT,
    new_full_address     TEXT,
    match_note           TEXT
);

CREATE INDEX IF NOT EXISTS idx_wam_portal_value ON ward_address_mappings(portal_ward_value);
CREATE INDEX IF NOT EXISTS idx_wam_old_ward_code ON ward_address_mappings(old_ward_code);
CREATE INDEX IF NOT EXISTS idx_wam_new_ward_code ON ward_address_mappings(new_ward_code);
CREATE INDEX IF NOT EXISTS idx_wam_new_ward_name ON ward_address_mappings(new_ward);
CREATE INDEX IF NOT EXISTS idx_wam_match_status ON ward_address_mappings(match_status);
