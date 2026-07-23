from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# peoplelink-apply/ (project root)
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
TEMPLATES_DIR = ROOT_DIR / "templates"

load_dotenv(ROOT_DIR / ".env")

DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "exports").mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("PEOPLELINK_DB_PATH", str(DATA_DIR / "peoplelink.db")))

PORTAL_BASE = os.getenv(
    "PEOPLELINK_PORTAL_BASE",
    "https://recruit.peoplelinkvietnam.com",
)
LOCATION_API_BASE = os.getenv(
    "PEOPLELINK_LOCATION_API_BASE",
    "https://api_adhoc.plsvn.com",
)
LOCATION_AUTH = os.getenv(
    "PEOPLELINK_LOCATION_AUTH",
    "Basic FlexibleProjects:0:0",
)

SUBMIT_DELAY_MS = int(os.getenv("PEOPLELINK_SUBMIT_DELAY_MS", "800"))

# Portal endpoints
URL_PROJECT_LIST = f"{PORTAL_BASE}/ProjectHeadcount/List"
URL_SEARCH_PROJECTS = f"{PORTAL_BASE}/ProjectHeadcount/Search_ProjectHeadcount"
URL_PROJECT_DETAIL = f"{PORTAL_BASE}/ProjectHeadcount/Detail/{{project_id}}"
URL_APPLY_REQUEST = f"{PORTAL_BASE}/ProjectHeadcount/ApplyRequest/{{apply_request_id}}"
URL_CANDIDATE_APPLY = f"{PORTAL_BASE}/ProjectHeadcount/Candidate_ApplyRequest_v2"

# Location API
URL_LIST_WARD = f"{LOCATION_API_BASE}/api/Admin_Manager/List_Ward"
# District endpoint will be confirmed in Location Sync step
URL_LIST_DISTRICT = f"{LOCATION_API_BASE}/api/Admin_Manager/List_District"

APP_NAME = "PeopleLink Apply Tool"
APP_VERSION = "0.1.0"
