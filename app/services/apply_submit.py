"""Build Candidate_ApplyRequest_v2 multipart payload (no HTTP submit here)."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.config import PORTAL_BASE, TEMPLATES_DIR, URL_CANDIDATE_APPLY
from app.services.user_service import ensure_app_user

APPLY_TEMPLATE_PATH = TEMPLATES_DIR / "apply_candidate.json"

# https://recruit.peoplelinkvietnam.com/ProjectHeadcount/ApplyRequest/2281
_APPLY_URL_RE = re.compile(
    r"/ProjectHeadcount/ApplyRequest/(\d+)/?",
    re.IGNORECASE,
)

_CANDIDATE_ALIASES: dict[str, tuple[str, ...]] = {
    "Mobile": ("Mobile", "mobile"),
    "FullName": ("FullName", "full_name"),
    "Sex": ("Sex", "sex"),
    "Birthday": ("Birthday", "birthday"),
    "AcademicLevel": ("AcademicLevel", "academic_level"),
    "Email": ("Email", "email"),
    "AddrTmpStreet": ("AddrTmpStreet", "addr_tmp_street"),
    "AddrTmpProvince": ("AddrTmpProvince", "addr_tmp_province"),
    "AddrTmpDistrict": ("AddrTmpDistrict", "addr_tmp_district"),
    "AddrTmpWard": ("AddrTmpWard", "addr_tmp_ward"),
    "Height": ("Height", "height"),
    "Weight": ("Weight", "weight"),
    "ApplyExperienceNote": ("ApplyExperienceNote", "apply_experience_note"),
    "WishWorkplace": ("WishWorkplace", "wish_workplace"),
    "PersonID": ("PersonID", "person_id"),
    "ProjectHeadcountID": ("ProjectHeadcountID", "project_headcount_id"),
    "ProjectHeadcountType": ("ProjectHeadcountType", "project_headcount_type"),
}


@dataclass
class ApplyRequestBuild:
    """Ready-to-send apply request — wire submit() later from frontend."""

    url: str
    method: str
    headers: dict[str, str]
    form_fields: list[tuple[str, str]]
    apply_request_id: int
    project_headcount_id: str
    referer: str
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "method": self.method,
            "headers": self.headers,
            "form_fields": [{"key": k, "value": v} for k, v in self.form_fields],
            "apply_request_id": self.apply_request_id,
            "project_headcount_id": self.project_headcount_id,
            "referer": self.referer,
            "meta": self.meta,
        }


def load_apply_template() -> dict[str, Any]:
    return json.loads(APPLY_TEMPLATE_PATH.read_text(encoding="utf-8"))


def parse_apply_request_id(apply_url: str) -> int:
    """
    Extract HeadcountReqRecruiterID from apply link.

    Example:
      https://recruit.peoplelinkvietnam.com/ProjectHeadcount/ApplyRequest/2239
      → 2239  (= HeadcountReqRecruiterID, dùng cho referer)
    ProjectHeadcountID lấy từ UI chọn dự án lúc đẩy (vd 176).
    """
    text = (apply_url or "").strip()
    if not text:
        raise ValueError("Chưa có apply URL.")

    match = _APPLY_URL_RE.search(text)
    if match:
        return int(match.group(1))

    if text.isdigit():
        return int(text)

    parsed = urlparse(text)
    match = _APPLY_URL_RE.search(parsed.path or "")
    if match:
        return int(match.group(1))

    raise ValueError(
        "URL không hợp lệ. Cần dạng "
        f"{PORTAL_BASE}/ProjectHeadcount/ApplyRequest/{{id}}"
    )


def build_apply_referer(apply_request_id: int) -> str:
    return f"{PORTAL_BASE}/ProjectHeadcount/ApplyRequest/{apply_request_id}"


def _pick(candidate: dict[str, Any], field: str, default: str = "") -> str:
    for key in _CANDIDATE_ALIASES.get(field, (field,)):
        if key in candidate and candidate[key] is not None:
            return str(candidate[key]).strip()
    return default


def _require_user_fields() -> tuple[str, str]:
    user = ensure_app_user()
    pic = (user.get("recruiter_pic") or "").strip()
    hrid = (user.get("headcount_request_id") or "").strip()
    if not pic:
        raise ValueError("User chưa có RecruiterPIC — điền ở section User trước.")
    if not hrid:
        raise ValueError(
            "User chưa có HeadcountRequestID — điền ở section User trước."
        )
    return pic, hrid


def build_apply_form_fields(
    *,
    headcount_req_recruiter_id: int,
    candidate: dict[str, Any],
    recruiter_pic: str,
    headcount_request_id: str,
) -> list[tuple[str, str]]:
    """
    Ordered multipart fields matching Postman `template`.

    - HeadcountReqRecruiterID = id trên ApplyRequest URL (vd 2239)
    - ProjectHeadcountID = từ UI chọn dự án lúc đẩy (vd 176) — KHÔNG lấy từ URL
    - RecruiterPIC / HeadcountRequestID = từ users
    """
    template = load_apply_template()
    defaults = {
        str(k): "" if v is None else str(v)
        for k, v in (template.get("static_defaults") or {}).items()
    }
    order: list[str] = list(template.get("field_order") or [])

    project_headcount_id = _pick(candidate, "ProjectHeadcountID")
    if not project_headcount_id:
        raise ValueError(
            "Thiếu ProjectHeadcountID — chọn dự án trên UI trước khi đẩy."
        )

    values: dict[str, str] = {
        **defaults,
        "HeadcountReqRecruiterID": str(headcount_req_recruiter_id),
        "RecruiterPIC": str(recruiter_pic),
        "HeadcountRequestID": str(headcount_request_id),
        "ProjectHeadcountID": project_headcount_id,
        "ProjectHeadcountType": _pick(candidate, "ProjectHeadcountType", "3"),
        "PersonID": _pick(candidate, "PersonID", defaults.get("PersonID", "")),
        "Mobile": _pick(candidate, "Mobile"),
        "FullName": _pick(candidate, "FullName"),
        "Sex": _pick(candidate, "Sex"),
        "Birthday": _pick(candidate, "Birthday"),
        "AcademicLevel": _pick(candidate, "AcademicLevel"),
        "Email": _pick(candidate, "Email"),
        "AddrTmpStreet": _pick(candidate, "AddrTmpStreet"),
        "AddrTmpProvince": _pick(candidate, "AddrTmpProvince"),
        "AddrTmpDistrict": _pick(candidate, "AddrTmpDistrict"),
        "AddrTmpWard": _pick(candidate, "AddrTmpWard"),
        "Height": _pick(candidate, "Height"),
        "Weight": _pick(candidate, "Weight"),
        "ApplyExperienceNote": _pick(candidate, "ApplyExperienceNote"),
        "WishWorkplace": _pick(
            candidate, "WishWorkplace", defaults.get("WishWorkplace", "")
        ),
        "chkAgreePolicy": defaults.get("chkAgreePolicy", "on"),
    }

    fields: list[tuple[str, str]] = []
    for key in order:
        fields.append((key, values.get(key, "")))
    return fields


def build_apply_headers(
    *,
    referer: str,
    cookie: str = "",
) -> dict[str, str]:
    """Headers for apply submit (cookie optional)."""
    headers = {
        "accept": "*/*",
        "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.6,en;q=0.5",
        "origin": PORTAL_BASE,
        "referer": referer,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
    }
    cookie_value = (cookie or "").strip()
    if cookie_value:
        headers["Cookie"] = cookie_value
    return headers


def build_apply_request(
    *,
    apply_url: str,
    candidate: dict[str, Any],
    cookie: str = "",
) -> ApplyRequestBuild:
    """
    Build full apply request from pasted ApplyRequest URL + candidate row.

    Does NOT send HTTP — call submit_apply_request() / submit_batch when user clicks.
    """
    apply_request_id = parse_apply_request_id(apply_url)
    recruiter_pic, headcount_request_id = _require_user_fields()
    referer = build_apply_referer(apply_request_id)
    form_fields = build_apply_form_fields(
        headcount_req_recruiter_id=apply_request_id,
        candidate=candidate,
        recruiter_pic=recruiter_pic,
        headcount_request_id=headcount_request_id,
    )
    headers = build_apply_headers(referer=referer, cookie=cookie)

    project_headcount_id = _pick(candidate, "ProjectHeadcountID")
    return ApplyRequestBuild(
        url=URL_CANDIDATE_APPLY,
        method="POST",
        headers=headers,
        form_fields=form_fields,
        apply_request_id=apply_request_id,
        project_headcount_id=project_headcount_id,
        referer=referer,
        meta={
            "template": str(APPLY_TEMPLATE_PATH.name),
            "apply_url_input": apply_url.strip(),
            "headcount_req_recruiter_id": str(apply_request_id),
            "project_headcount_id": project_headcount_id,
            "recruiter_pic": recruiter_pic,
            "headcount_request_id": headcount_request_id,
        },
    )


@dataclass
class ApplySubmitResult:
    candidate_id: int
    row_no: int
    full_name: str
    status: str  # success | failed
    http_status: int | None = None
    response_body: str = ""
    error: str = ""


def interpret_apply_response(http_status: int, body: str) -> tuple[str, str]:
    """
    Return (status, error_message).
    Portal may return HTTP 200 with JSON {"result":"Error", "msg":...}.
    """
    text = (body or "").strip()
    if http_status >= 400:
        return "failed", f"HTTP {http_status}"

    try:
        payload = json.loads(text) if text else None
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        result = str(payload.get("result") or payload.get("Result") or "").strip()
        msg = str(
            payload.get("msg")
            or payload.get("Message")
            or payload.get("message")
            or ""
        ).strip()
        err = str(payload.get("err") or payload.get("Error") or "").strip()
        if result.lower() in {"error", "failed", "fail"}:
            detail = " | ".join(x for x in (msg, err) if x) or "Portal result=Error"
            return "failed", detail
        if result.lower() in {"success", "ok"}:
            return "success", ""

    # Non-JSON or unknown shape with HTTP OK
    if "ứng tuyển không thành công" in text.lower() or '"result":"error"' in text.lower():
        return "failed", text[:300]
    return "success", ""


def submit_apply_request(built: ApplyRequestBuild) -> tuple[int, str]:
    """
    POST multipart to Candidate_ApplyRequest_v2.
    Only call from UI button — do not auto-run.
    """
    import httpx

    # Duplicate keys (chkAgreePolicy x2) → use files list so httpx keeps both.
    files = [(key, (None, value)) for key, value in built.form_fields]
    headers = {
        k: v
        for k, v in built.headers.items()
        if k.lower() not in {"content-type", "content-length"}
    }

    with httpx.Client(timeout=60.0, verify=False, follow_redirects=True) as client:
        response = client.post(built.url, files=files, headers=headers)

    return response.status_code, response.text


def submit_batch_candidates(
    batch_id: int,
    *,
    cookie: str = "",
    project_headcount_id: str | None = None,
    only_statuses: set[str] | frozenset[str] | None = None,
    delay_ms: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[ApplySubmitResult]:
    """
    Push candidates in a saved batch to the portal apply endpoint.
    Updates candidates.status / response_body / error / submitted_at.

    project_headcount_id: nếu truyền (từ UI chọn dự án khi đẩy) → ghi đè
    ProjectHeadcountID trên mọi dòng được đẩy.
    Cookie không bắt buộc khi đẩy apply.

    only_statuses:
      - None → đẩy mọi dòng chưa success (pending / failed / invalid)
      - {"failed"} → chỉ đẩy lại dòng lỗi
    """
    import time
    from datetime import datetime, timezone

    from app.config import SUBMIT_DELAY_MS
    from app.db import get_conn
    from app.services.excel_io import PAYLOAD_COLUMNS, list_imported_candidates

    override_project_id = (project_headcount_id or "").strip()
    if not override_project_id:
        raise ValueError("Chọn dự án (ProjectHeadcountID) trước khi đẩy.")

    items = list_imported_candidates(batch_id=batch_id)
    if not items:
        raise ValueError(f"Batch #{batch_id} không có ứng viên.")

    if only_statuses is None:
        allowed = {"pending", "failed", "invalid"}
    else:
        allowed = {str(s).strip().lower() for s in only_statuses if str(s).strip()}

    items = [
        it
        for it in items
        if str(it.get("_status") or "pending").strip().lower() in allowed
    ]
    if not items:
        raise ValueError(
            "Không còn dòng nào khớp bộ lọc để đẩy "
            f"(statuses={sorted(allowed)})."
        )

    wait_s = (SUBMIT_DELAY_MS if delay_ms is None else delay_ms) / 1000.0
    results: list[ApplySubmitResult] = []

    with get_conn() as conn:
        conn.execute(
            "UPDATE import_batches SET status = 'running' WHERE id = ?",
            (batch_id,),
        )

    for i, item in enumerate(items):
        cid = int(item["_id"])
        row_no = int(item.get("_row_no") or i + 1)
        full_name = str(item.get("FullName") or "")
        apply_url = str(item.get("ApplyURL") or "").strip()
        payload = {col: str(item.get(col) or "") for col in PAYLOAD_COLUMNS}
        payload["ProjectHeadcountID"] = override_project_id

        if progress:
            progress(f"[{i + 1}/{len(items)}] {full_name or f'row {row_no}'}")

        submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = ApplySubmitResult(
            candidate_id=cid,
            row_no=row_no,
            full_name=full_name,
            status="failed",
        )

        try:
            if not apply_url:
                raise ValueError("Thiếu ApplyURL trên dòng ứng viên.")
            built = build_apply_request(
                apply_url=apply_url,
                candidate=payload,
                cookie=cookie,
            )
            http_status, body = submit_apply_request(built)
            result.http_status = http_status
            result.response_body = body
            status, err = interpret_apply_response(http_status, body)
            result.status = status
            result.error = err
        except Exception as exc:  # noqa: BLE001
            result.status = "failed"
            result.error = str(exc)
            result.response_body = result.response_body or ""

        with get_conn() as conn:
            conn.execute(
                """
                UPDATE candidates
                SET status = ?, error = ?, response_body = ?, submitted_at = ?
                WHERE id = ?
                """,
                (
                    result.status,
                    result.error or None,
                    result.response_body,
                    submitted_at,
                    cid,
                ),
            )

        results.append(result)
        if i < len(items) - 1 and wait_s > 0:
            time.sleep(wait_s)

    with get_conn() as conn:
        statuses = [
            str(r["status"] or "pending")
            for r in conn.execute(
                "SELECT status FROM candidates WHERE batch_id = ?",
                (batch_id,),
            ).fetchall()
        ]
        if all(s == "success" for s in statuses):
            final_status = "done"
        elif any(s == "failed" for s in statuses):
            final_status = "done_with_errors"
        elif any(s == "pending" for s in statuses):
            final_status = "partial"
        else:
            final_status = "done"
        conn.execute(
            "UPDATE import_batches SET status = ? WHERE id = ?",
            (final_status, batch_id),
        )

    return results
