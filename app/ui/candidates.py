"""Unified candidates workspace: import → edit → save → push in one flow."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.services.address_resolve import (
    ADDR_STATUS_CONFIRMED,
    ADDR_STATUS_NEW,
    ADDR_STATUS_OLD,
    ADDR_STATUS_PARTIAL,
    ADDR_STATUS_UNRESOLVED,
    STATUS_ICON,
    apply_suggestion_to_row,
    enrich_row_address,
    enrich_rows,
    mark_address_kept,
    suggestions_for_row,
)
from app.services.apply_submit import submit_batch_candidates
from app.services.excel_io import (
    PAYLOAD_COLUMNS,
    delete_import_batch,
    export_candidate_template_bytes,
    export_imported_candidates_bytes,
    list_import_batches,
    list_imported_candidates,
    load_batch_as_draft,
    parse_candidates_excel,
    save_candidates_batch,
    update_candidates_batch,
)
from app.services.locations import (
    district_id_from_value,
    district_option_value,
    list_districts,
    list_provinces,
    list_wards,
    province_code_from_value,
    province_option_value,
    resolve_location_fields,
    ward_option_value,
)
from app.services.user_service import list_user_projects
from app.services.submitted_candidates import annotate_rows_submitted
from app.services.project_service import get_project

# Visible grid: import fields + address resolve status + submit result
_GRID_COLUMNS = [
    "Submitted",
    "AddressIcon",
    "FullName",
    "Mobile",
    "FullAddress",
    "AddrTmpStreet",
    "AddrTmpProvince",
    "AddrTmpDistrict",
    "AddrTmpWard",
    "Sex",
    "Birthday",
    "AcademicLevel",
    "Email",
    "Height",
    "Weight",
    "ApplyExperienceNote",
    "WishWorkplace",
    "ProjectHeadcountType",
    "AddressNote",
    "SubmitStatus",
    "SubmitError",
]

_META_KEYS = ("_candidate_id", "SubmitStatus", "SubmitError")

# Key widget data_editor — giữ ổn định; chỉ xóa khi mở/đóng batch hoặc commit có chủ đích
_EDITOR_KEY = "draft_candidates_editor_v8"
_EDITOR_KEYS_LEGACY = (
    "draft_candidates_editor_v4",
    "draft_candidates_editor_v5",
    "draft_candidates_editor_v6",
    "draft_candidates_editor_v7",
    _EDITOR_KEY,
)


def _ensure_state() -> None:
    defaults = {
        "draft_candidates": [],
        "draft_filename": "",
        "draft_batch_id": None,
        "addr_edit_idx": 0,
        "last_submit_results": [],
        "ws_mode": "pick",  # pick | edit
        "grid_working_rows": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_editor_widgets() -> None:
    for key in _EDITOR_KEYS_LEGACY:
        st.session_state.pop(key, None)
    st.session_state.pop("grid_working_rows", None)
    for k in list(st.session_state.keys()):
        if str(k).startswith("addr_"):
            del st.session_state[k]


def _open_batch(batch_id: int) -> None:
    rows, filename = load_batch_as_draft(batch_id)
    st.session_state.draft_candidates = annotate_rows_submitted(
        enrich_rows(rows, force=False)
    )
    st.session_state.draft_filename = filename
    st.session_state.draft_batch_id = batch_id
    st.session_state.addr_edit_idx = 0
    st.session_state.ws_mode = "edit"
    _clear_editor_widgets()


def _close_draft() -> None:
    st.session_state.draft_candidates = []
    st.session_state.draft_filename = ""
    st.session_state.draft_batch_id = None
    st.session_state.addr_edit_idx = 0
    st.session_state.ws_mode = "pick"
    _clear_editor_widgets()


def _draft_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=_GRID_COLUMNS)
    frame = pd.DataFrame(rows)
    for col in _GRID_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    return frame[_GRID_COLUMNS]


def _rows_from_editor(
    edited_df: pd.DataFrame,
    previous: list[dict],
    *,
    auto_enrich: bool = False,
) -> list[dict[str, str]]:
    """Merge editor columns with hidden/runtime fields from previous draft.

    auto_enrich=False (mặc định): không resolve địa chỉ khi đang gõ/dán —
    tránh remount lưới và mất dữ liệu vừa nhập.
    """
    working: list[dict[str, str]] = []
    for i, (_, series) in enumerate(edited_df.iterrows()):
        prev = previous[i] if i < len(previous) else {}
        row = {col: str(prev.get(col) or "") for col in PAYLOAD_COLUMNS}
        for key in _META_KEYS:
            if prev.get(key) is not None:
                row[key] = str(prev.get(key) or "")
        for col in _GRID_COLUMNS:
            if col in series.index:
                val = series.get(col)
                row[col] = "" if pd.isna(val) else str(val).strip()
            # Giữ AddressStatus/Icon/Note từ prev nếu cột không nằm trên lưới edit
        for extra in ("AddressStatus", "AddressIcon", "AddressNote"):
            if extra not in row or not row.get(extra):
                if prev.get(extra) is not None:
                    row[extra] = str(prev.get(extra) or "")
        if not any(
            str(v).strip()
            for k, v in row.items()
            if k not in _META_KEYS and k not in {"SubmitStatus", "SubmitError"}
        ):
            continue
        if not row.get("ProjectHeadcountType"):
            row["ProjectHeadcountType"] = "3"
        if not row.get("SubmitStatus"):
            row["SubmitStatus"] = str(prev.get("SubmitStatus") or "pending")
        if not row.get("SubmitError"):
            row["SubmitError"] = str(prev.get("SubmitError") or "")
        if auto_enrich:
            prev_full = str(prev.get("FullAddress") or "").strip()
            new_full = str(row.get("FullAddress") or "").strip()
            if new_full and new_full != prev_full:
                row["AddressStatus"] = ""
                row = enrich_row_address(row, force=True)
            elif not row.get("AddressStatus"):
                row = enrich_row_address(row, force=False)
        working.append(row)
    return working


def _get_editor_working_rows(*, auto_enrich: bool = False) -> list[dict]:
    """Đọc dữ liệu hiện tại từ widget data_editor (nếu có), không ghi đè draft."""
    draft = list(st.session_state.get("draft_candidates") or [])
    edited = st.session_state.get(_EDITOR_KEY)
    if isinstance(edited, pd.DataFrame):
        rows = _rows_from_editor(edited, draft, auto_enrich=auto_enrich)
        rows = annotate_rows_submitted(rows)
        st.session_state.grid_working_rows = rows
        return rows
    cached = st.session_state.get("grid_working_rows")
    if isinstance(cached, list) and cached:
        return annotate_rows_submitted(cached)
    return annotate_rows_submitted(draft)


def _commit_working_rows(rows: list[dict], *, clear_editor: bool = True) -> None:
    """Ghi nhận lưới vào draft (sau Lưu / Đẩy / Áp dụng địa chỉ / Quét lại)."""
    stamped = annotate_rows_submitted(rows)
    st.session_state.draft_candidates = stamped
    st.session_state.grid_working_rows = stamped
    if clear_editor:
        for key in _EDITOR_KEYS_LEGACY:
            st.session_state.pop(key, None)


def _attach_candidate_ids(rows: list[dict], candidate_ids: list[int]) -> list[dict]:
    out = []
    for i, row in enumerate(rows):
        item = dict(row)
        if i < len(candidate_ids):
            item["_candidate_id"] = str(candidate_ids[i])
        if not item.get("SubmitStatus"):
            item["SubmitStatus"] = "pending"
        out.append(item)
    return out


def _reload_draft_from_batch(batch_id: int) -> None:
    rows, filename = load_batch_as_draft(batch_id)
    st.session_state.draft_candidates = annotate_rows_submitted(
        enrich_rows(rows, force=False)
    )
    st.session_state.draft_filename = filename
    st.session_state.draft_batch_id = batch_id
    _clear_editor_widgets()


def _project_choice_label(project: dict) -> str:
    pid = project.get("project_id")
    code = (project.get("project_code") or "").strip() or "?"
    name = (project.get("project_name") or "").strip() or "(không tên)"
    if len(name) > 64:
        name = name[:61] + "..."
    expired = " · hết hạn" if int(project.get("is_expired") or 0) else ""
    return f"{pid} · {code} · {name}{expired}"


@st.dialog("Xóa batch")
def _delete_batch_modal(batch_id: int, filename: str = "", candidate_count: int = 0) -> None:
    st.markdown(f"Xóa vĩnh viễn batch **#{batch_id}**?")
    if filename:
        st.caption(f"File: `{filename}`")
    if candidate_count:
        st.caption(f"Sẽ xóa **{candidate_count}** ứng viên trong batch.")
    st.warning("Không hoàn tác được.")

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Xóa", type="primary", use_container_width=True, key="dlg_del_yes"):
            try:
                result = delete_import_batch(int(batch_id))
                if st.session_state.get("draft_batch_id") == int(batch_id):
                    _close_draft()
                st.session_state.last_submit_results = []
                st.session_state["ws_delete_flash"] = (
                    f"Đã xóa batch #{result['batch_id']} "
                    f"({result['deleted_candidates']} UV) · {result['filename']}"
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    with col_no:
        if st.button("Hủy", use_container_width=True, key="dlg_del_no"):
            st.rerun()


def _batch_meta(batches: list[dict], batch_id: int) -> tuple[str, int]:
    for b in batches:
        if int(b["id"]) == int(batch_id):
            return str(b.get("filename") or ""), int(b.get("candidate_count") or 0)
    return "", 0


def _render_pick_screen(batches: list[dict]) -> None:
    st.markdown("### Bắt đầu")
    left, right = st.columns(2)

    with left:
        st.markdown("**Mở batch đã lưu**")
        if not batches:
            st.info("Chưa có batch. Import Excel ở cột bên phải.")
        else:
            labels = {
                (
                    f"#{b['id']} · {b['filename']} · {b['candidate_count']} UV · "
                    f"{b['status']} · ✓{int(b.get('success_count') or 0)} "
                    f"✗{int(b.get('failed_count') or 0)} "
                    f"⏳{int(b.get('pending_count') or 0)}"
                ): b["id"]
                for b in batches
            }
            choice = st.selectbox(
                "Batch",
                options=list(labels.keys()),
                key="ws_open_batch",
                label_visibility="collapsed",
            )
            open_c, del_c = st.columns(2)
            with open_c:
                if st.button("Mở batch", type="primary", use_container_width=True):
                    _open_batch(labels[choice])
                    st.rerun()
            with del_c:
                if st.button("Xóa batch", type="secondary", use_container_width=True):
                    bid = int(labels[choice])
                    fname, count = _batch_meta(batches, bid)
                    _delete_batch_modal(bid, fname, count)

            flash = st.session_state.pop("ws_delete_flash", None)
            if flash:
                st.success(flash)

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "id": b["id"],
                            "file": b["filename"],
                            "UV": b["candidate_count"],
                            "status": b["status"],
                            "ok": int(b.get("success_count") or 0),
                            "fail": int(b.get("failed_count") or 0),
                            "pending": int(b.get("pending_count") or 0),
                        }
                        for b in batches
                    ]
                ),
                use_container_width=True,
                hide_index=True,
                height=220,
            )

    with right:
        st.markdown("**Import Excel mới**")
        st.download_button(
            "Tải template Excel",
            data=export_candidate_template_bytes(),
            file_name="candidates_import_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        uploaded = st.file_uploader(
            "Chọn file .xlsx",
            type=["xlsx"],
            key="ws_candidates_upload",
        )
        if uploaded is not None:
            if st.button(
                "Nạp vào lưới",
                type="primary",
                use_container_width=True,
            ):
                try:
                    rows = annotate_rows_submitted(parse_candidates_excel(uploaded.getvalue()))
                    for r in rows:
                        r["SubmitStatus"] = "pending"
                        r["SubmitError"] = ""
                        r.pop("_candidate_id", None)
                    st.session_state.draft_candidates = rows
                    st.session_state.draft_filename = uploaded.name
                    st.session_state.draft_batch_id = None
                    st.session_state.addr_edit_idx = 0
                    st.session_state.ws_mode = "edit"
                    st.session_state.last_submit_results = []
                    _clear_editor_widgets()
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

        if batches:
            export_labels = {"Tất cả batch": None}
            for b in batches:
                export_labels[f"#{b['id']} · {b['filename']}"] = b["id"]
            export_choice = st.selectbox(
                "Export",
                options=list(export_labels.keys()),
                key="ws_export_choice",
            )
            export_id = export_labels[export_choice]
            exported = list_imported_candidates(batch_id=export_id)
            st.download_button(
                "Export Excel",
                data=export_imported_candidates_bytes(batch_id=export_id),
                file_name=(
                    f"candidates_batch_{export_id}.xlsx"
                    if export_id
                    else "candidates_all.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                ),
                disabled=len(exported) == 0,
                use_container_width=True,
            )


@st.dialog("Gợi ý địa chỉ cũ")
def _address_suggest_modal(row_idx: int, row: dict) -> None:
    full = str(row.get("FullAddress") or "")
    name = str(row.get("FullName") or f"dòng #{row_idx + 1}")
    st.markdown(f"**{name}**")
    st.caption(f"Địa chỉ nhập: `{full}`")

    suggestions = suggestions_for_row(row)
    if not suggestions:
        st.warning("Không có gợi ý mapping. Có thể import mapping CSV ở tab Thiết lập.")
        if st.button("Đóng", use_container_width=True):
            st.rerun()
        return

    labels = []
    for i, s in enumerate(suggestions):
        mark = " (mặc định)" if s.is_default else ""
        kind = f" · {s.mapping_type}" if s.mapping_type else ""
        labels.append(f"{i + 1}. {s.label}{mark}{kind}")

    choice = st.radio(
        "Chọn địa chỉ cũ để map",
        options=list(range(len(suggestions))),
        format_func=lambda i: labels[i],
        key=f"addr_sug_radio_{row_idx}",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Xác nhận map", type="primary", use_container_width=True):
            try:
                draft = _get_editor_working_rows(auto_enrich=False)
                if row_idx >= len(draft):
                    raise IndexError("Dòng không còn trong lưới")
                draft[row_idx] = apply_suggestion_to_row(
                    draft[row_idx], suggestions[choice]
                )
                _commit_working_rows(draft, clear_editor=True)
                st.session_state["ws_addr_flash"] = (
                    f"Đã map dòng #{row_idx + 1} → địa chỉ cũ."
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    with c2:
        if st.button("Giữ nguyên", use_container_width=True):
            draft = _get_editor_working_rows(auto_enrich=False)
            if row_idx < len(draft):
                draft[row_idx] = mark_address_kept(draft[row_idx])
                _commit_working_rows(draft, clear_editor=True)
                st.session_state["ws_addr_flash"] = (
                    f"Giữ nguyên dòng #{row_idx + 1} (chưa map)."
                )
            st.rerun()
    with c3:
        if st.button("Đóng", use_container_width=True):
            st.rerun()


def _province_options() -> list[str]:
    return [
        province_option_value(p)
        for p in list_provinces()
        if province_option_value(p)
    ]


def _district_options(province_value: str) -> list[str]:
    code = province_code_from_value(province_value)
    if not code:
        return []
    return [district_option_value(d) for d in list_districts(code)]


def _ward_options(district_value: str, province_value: str) -> list[str]:
    code = province_code_from_value(province_value)
    did = district_id_from_value(district_value, code)
    if did is None:
        return []
    return [ward_option_value(w) for w in list_wards(did)]


def _normalize_province_value(value: str, prov_opts: list[str]) -> str:
    text = (value or "").strip()
    if not text:
        return prov_opts[0] if prov_opts else ""
    if text in prov_opts:
        return text
    code = province_code_from_value(text)
    if code:
        for p in list_provinces():
            if p["code"] == code:
                return province_option_value(p)
    return text if text in prov_opts else (prov_opts[0] if prov_opts else text)


def _normalize_district_value(
    value: str, province_value: str, dist_opts: list[str]
) -> str:
    text = (value or "").strip()
    if text and text in dist_opts:
        return text
    code = province_code_from_value(province_value)
    did = district_id_from_value(text, code)
    if did is not None and code:
        for d in list_districts(code):
            if int(d["id"]) == did:
                return district_option_value(d)
    return dist_opts[0] if dist_opts else ""


def _normalize_ward_value(
    value: str, district_value: str, province_value: str, ward_opts: list[str]
) -> str:
    text = (value or "").strip()
    if text and text in ward_opts:
        return text
    code = province_code_from_value(province_value)
    did = district_id_from_value(district_value, code)
    if did is not None and text:
        raw = text.split("|", 1)[0].strip()
        for w in list_wards(did):
            if (
                str(w["inserted_value"]) == raw
                or str(w["id"]) == raw
                or w["name"] == text
                or ward_option_value(w) == text
            ):
                return ward_option_value(w)
    return ward_opts[0] if ward_opts else ""


def _render_address_panel(working_rows: list[dict]) -> list[dict]:
    flagged = [
        (i, r)
        for i, r in enumerate(working_rows)
        if (r.get("AddressStatus") or "") in {ADDR_STATUS_NEW, ADDR_STATUS_UNRESOLVED}
        or (r.get("AddressIcon") or "") == "★"
    ]
    n_new = sum(
        1 for _, r in flagged if (r.get("AddressStatus") or "") == ADDR_STATUS_NEW
    )
    n_bad = sum(
        1
        for _, r in flagged
        if (r.get("AddressStatus") or "") == ADDR_STATUS_UNRESOLVED
    )

    st.markdown("### Địa chỉ")
    st.markdown(
        '<p class="pl-addr-desc">'
        "Excel chỉ cần <b>FullAddress</b> một dòng. "
        "✓ đủ · … thiếu phường · ★ cần gợi ý · ? chưa nhận ra."
        "</p>",
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns([1, 1, 1, 1.2])
    m1.metric("★ Cần gợi ý", n_new)
    m2.metric("? Chưa nhận", n_bad)
    m3.metric("Tổng dòng", len(working_rows))
    with m4:
        st.write("")
        if st.button(
            "Quét lại từ FullAddress",
            use_container_width=True,
            help="Chỉ quét dòng chưa có ✓ (đã áp dụng / map xong thì bỏ qua)",
        ):
            before = _get_editor_working_rows(auto_enrich=False)
            skipped = sum(
                1
                for r in before
                if (r.get("AddressIcon") or "").strip() == "✓"
                or (r.get("AddressStatus") or "")
                in {ADDR_STATUS_OLD, ADDR_STATUS_CONFIRMED}
            )
            working_rows = enrich_rows(before, force=False, skip_ticked=True)
            _commit_working_rows(working_rows, clear_editor=True)
            scanned = max(0, len(before) - skipped)
            st.session_state["ws_addr_flash"] = (
                f"Đã quét {scanned} dòng · bỏ qua {skipped} dòng đã ✓."
            )
            st.rerun()

    # —— Bước 1 & 2: cùng layout card, chỉ khác badge + nội dung ——
    with st.container(border=True):
        st.markdown(
            """
<div class="pl-addr-head">
  <span class="pl-addr-kicker pl-addr-kicker--1">Bước 1 · Tự động</span>
  <h3 class="pl-addr-title">Gợi ý map địa chỉ mới → cũ</h3>
  <p class="pl-addr-desc">
    Dành cho dòng đánh dấu <b>★</b> hoặc <b>?</b>.
    Chọn gợi ý để quy đổi sang tỉnh / huyện / phường portal nhận được.
  </p>
</div>
            """,
            unsafe_allow_html=True,
        )
        if not flagged:
            st.success("Không còn dòng ★ / ? — có thể bỏ qua bước này.")
        else:
            st.warning(f"Còn **{len(flagged)}** dòng cần xem gợi ý.")
            for i, row in flagged:
                label = (
                    f"{row.get('AddressIcon') or '?'}  **#{i + 1}** · "
                    f"{row.get('FullName') or '(chưa tên)'}"
                )
                b1, b2 = st.columns([4, 1.1], vertical_alignment="center")
                with b1:
                    st.markdown(label)
                    st.caption((row.get("FullAddress") or "")[:100])
                    if row.get("AddressNote"):
                        st.caption(str(row.get("AddressNote")))
                with b2:
                    if st.button(
                        "Chọn gợi ý",
                        key=f"addr_open_sug_{i}",
                        use_container_width=True,
                        type="primary",
                    ):
                        _address_suggest_modal(i, row)

    st.markdown('<div class="pl-addr-gap"></div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(
            """
<div class="pl-addr-head">
  <span class="pl-addr-kicker pl-addr-kicker--2">Bước 2 · Thủ công</span>
  <h3 class="pl-addr-title">Sửa địa chỉ bằng dropdown</h3>
  <p class="pl-addr-desc">
    Chọn dòng → Tỉnh → Huyện → Phường → <b>Áp dụng</b>.
    Huyện bắt buộc; phường có thể để trống.
  </p>
</div>
            """,
            unsafe_allow_html=True,
        )
        row_labels = [
            f"#{i + 1} {r.get('AddressIcon') or ''} — "
            f"{r.get('FullName') or '(chưa tên)'} — "
            f"{(r.get('FullAddress') or r.get('AddrTmpProvince') or '')[:60]}"
            for i, r in enumerate(working_rows)
        ]
        idx = st.selectbox(
            "Chọn dòng cần sửa",
            options=list(range(len(working_rows))),
            format_func=lambda i: row_labels[i],
            key="addr_manual_row_select",
        )
        st.session_state.addr_edit_idx = idx
        row = working_rows[idx]

        province_opts = _province_options()
        current_prov = _normalize_province_value(
            row.get("AddrTmpProvince") or "", province_opts
        )
        col_p, col_c, col_w = st.columns(3)
        with col_p:
            new_prov = st.selectbox(
                "Tỉnh / Thành phố",
                options=province_opts or [""],
                index=(
                    province_opts.index(current_prov)
                    if current_prov in province_opts
                    else 0
                ),
                key=f"addr_prov_sel_{idx}",
            )
        prov_code = province_code_from_value(new_prov) or "none"
        dist_opts = _district_options(new_prov)

        with col_c:
            if not dist_opts:
                st.selectbox(
                    "Huyện / TP / Quận",
                    options=["(sync location trước)"],
                    disabled=True,
                    key=f"addr_dist_empty_{idx}_{prov_code}",
                )
                new_dist = ""
            else:
                current_dist = _normalize_district_value(
                    row.get("AddrTmpDistrict") or "", new_prov, dist_opts
                )
                new_dist = st.selectbox(
                    f"Huyện / TP / Quận ({len(dist_opts)})",
                    options=dist_opts,
                    index=(
                        dist_opts.index(current_dist)
                        if current_dist in dist_opts
                        else 0
                    ),
                    key=f"addr_dist_sel_{idx}_{prov_code}",
                )

        ward_opts = _ward_options(new_dist, new_prov) if new_dist else []
        dist_id = (
            district_id_from_value(new_dist, province_code_from_value(new_prov)) or 0
        )
        with col_w:
            ward_choices = ["(để trống — điền sau)"] + ward_opts
            if not new_dist or not ward_opts:
                st.selectbox(
                    "Phường / Xã",
                    options=["(chọn huyện trước)"],
                    disabled=True,
                    key=f"addr_ward_empty_{idx}_{prov_code}_{dist_id}",
                )
                new_ward = ""
            else:
                current_ward = _normalize_ward_value(
                    row.get("AddrTmpWard") or "", new_dist, new_prov, ward_opts
                )
                default_idx = 0
                if current_ward in ward_opts:
                    default_idx = ward_opts.index(current_ward) + 1
                picked = st.selectbox(
                    f"Phường / Xã ({len(ward_opts)})",
                    options=ward_choices,
                    index=default_idx,
                    key=f"addr_ward_sel_{idx}_{prov_code}_{dist_id}",
                )
                new_ward = "" if picked.startswith("(để trống") else picked

        if st.button(
            "Áp dụng địa chỉ cho dòng này",
            type="primary",
            use_container_width=True,
        ):
            if not new_prov or not new_dist:
                st.error("Cần chọn ít nhất Tỉnh và Huyện/TP/Quận.")
            else:
                working_rows = _get_editor_working_rows(auto_enrich=False)
                if idx >= len(working_rows):
                    st.error("Dòng không còn trong lưới — thử chọn lại.")
                else:
                    working_rows[idx]["AddrTmpProvince"] = new_prov
                    working_rows[idx]["AddrTmpDistrict"] = new_dist
                    working_rows[idx]["AddrTmpWard"] = new_ward
                    working_rows[idx].update(resolve_location_fields(working_rows[idx]))
                    if new_ward:
                        working_rows[idx]["AddressStatus"] = ADDR_STATUS_OLD
                        working_rows[idx]["AddressIcon"] = STATUS_ICON[ADDR_STATUS_OLD]
                        working_rows[idx]["AddressNote"] = (
                            "Đã chọn thủ công Province/District/Ward"
                        )
                    else:
                        working_rows[idx]["AddressStatus"] = ADDR_STATUS_PARTIAL
                        working_rows[idx]["AddressIcon"] = STATUS_ICON[
                            ADDR_STATUS_PARTIAL
                        ]
                        working_rows[idx]["AddressNote"] = (
                            "Đã chọn tỉnh + huyện — phường để trống (điền sau)"
                        )
                    _commit_working_rows(working_rows, clear_editor=True)
                    st.success(f"Đã áp dụng địa chỉ dòng #{idx + 1}.")
                    st.rerun()

    return working_rows


def _persist_working_rows(
    working_rows: list[dict],
    *,
    batch_id: int | None,
    filename: str,
) -> int:
    final_rows = []
    for r in working_rows:
        item = dict(r)
        item.update(resolve_location_fields(item))
        final_rows.append(item)
    if batch_id is not None:
        result = update_candidates_batch(int(batch_id), final_rows)
    else:
        result = save_candidates_batch(
            final_rows,
            filename=filename or "manual.xlsx",
        )
    stamped = _attach_candidate_ids(final_rows, result.get("candidate_ids") or [])
    _commit_working_rows(stamped, clear_editor=True)
    st.session_state.draft_batch_id = result["batch_id"]
    return int(result["batch_id"])


def _count_submit_status(rows: list[dict]) -> tuple[int, int, int]:
    ok = fail = pending = 0
    for r in rows:
        status = str(r.get("SubmitStatus") or "pending").strip().lower()
        if status == "success":
            ok += 1
        elif status == "failed":
            fail += 1
        else:
            pending += 1
    return ok, fail, pending


def _render_push_panel(
    batch_id: int,
    candidate_count: int,
    *,
    working_rows: list[dict],
    filename: str,
) -> None:
    st.markdown("### Đẩy lên portal")
    batch_label = f"#{batch_id}" if batch_id else "(sẽ tạo batch mới khi đẩy)"
    ok_n, fail_n, pending_n = _count_submit_status(working_rows)
    st.caption(
        f"Batch **{batch_label}** · {candidate_count} ứng viên · "
        f"✓ {ok_n} · ✗ {fail_n} · chờ {pending_n}. "
        "Ấn đẩy sẽ **tự lưu lưới** (giữ status từng dòng) rồi gửi. "
        "Dòng đã **success** được bỏ qua."
    )

    pending_addr = [
        r
        for r in working_rows
        if (r.get("AddressStatus") or "") == ADDR_STATUS_NEW
        or (r.get("AddressIcon") or "") == "★"
    ]
    if pending_addr:
        st.warning(
            f"Còn **{len(pending_addr)}** dòng ★ địa chỉ mới chưa xác nhận map. "
            "Nên xử lý gợi ý trước khi đẩy (portal chỉ nhận địa chỉ cũ)."
        )

    user_projects = list_user_projects()
    active = [p for p in user_projects if not int(p.get("is_expired") or 0)]
    pool = active or user_projects
    project_placeholder = "— Chọn dự án —"
    selected_project_id = ""

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        if not pool:
            st.warning("Chưa có project gắn user — vào tab Thiết lập → Sync Projects.")
        else:
            labels = {_project_choice_label(p): str(p["project_id"]) for p in pool}
            options = [project_placeholder, *labels.keys()]
            if st.session_state.get("ws_submit_project") not in options:
                st.session_state.ws_submit_project = project_placeholder
            choice = st.selectbox(
                "Dự án (bắt buộc)",
                options=options,
                key="ws_submit_project",
            )
            if choice == project_placeholder:
                selected_project_id = ""
                st.caption("Phải chọn dự án trước khi đẩy — không có mặc định.")
            else:
                selected_project_id = labels[choice]
                proj = get_project(int(selected_project_id))
                link = (proj or {}).get("link_apply") or ""
                if link:
                    st.caption(
                        f"ProjectHeadcountID=`{selected_project_id}` · "
                        f"Link Apply đã có."
                    )
                else:
                    st.error(
                        f"Project `{selected_project_id}` chưa có Link Apply — "
                        "vào tab Projects → Xem chi tiết để điền."
                    )
    with c2:
        st.metric("Chờ đẩy", pending_n)
    with c3:
        st.metric("Lỗi", fail_n)
    with c4:
        st.metric("OK", ok_n)

    push_n = pending_n + fail_n
    has_link = True
    if selected_project_id:
        proj = get_project(int(selected_project_id))
        has_link = bool((proj or {}).get("link_apply"))
    b1, b2 = st.columns(2)
    with b1:
        push = st.button(
            f"Đẩy chưa thành công ({push_n})",
            type="primary",
            use_container_width=True,
            disabled=not selected_project_id or not has_link or push_n == 0,
        )
    with b2:
        retry = st.button(
            f"Đẩy lại dòng lỗi ({fail_n})",
            use_container_width=True,
            disabled=not selected_project_id or not has_link or fail_n == 0,
        )

    def _run_push(*, only_failed: bool) -> None:
        if not selected_project_id:
            st.error("Bắt buộc chọn dự án trước khi đẩy.")
            return
        log = st.empty()
        try:
            saved_id = _persist_working_rows(
                working_rows,
                batch_id=batch_id or None,
                filename=filename,
            )
            only_statuses = {"failed"} if only_failed else None
            label = "dòng lỗi" if only_failed else "dòng chưa success"
            with st.spinner(f"Đang đẩy {label} batch #{saved_id}..."):
                results = submit_batch_candidates(
                    saved_id,
                    project_headcount_id=selected_project_id,
                    only_statuses=only_statuses,
                    progress=lambda msg: log.write(msg),
                )
            st.session_state.last_submit_results = [
                {
                    "candidate_id": r.candidate_id,
                    "row_no": r.row_no,
                    "full_name": r.full_name,
                    "status": r.status,
                    "http_status": r.http_status,
                    "error": r.error,
                    "response_body": r.response_body,
                }
                for r in results
            ]
            ok = sum(1 for r in results if r.status == "success")
            fail = len(results) - ok
            msg = (
                f"Xong batch #{saved_id} (project={selected_project_id}): "
                f"success={ok}, failed={fail}"
            )
            _reload_draft_from_batch(saved_id)
            if fail:
                st.session_state["ws_push_flash"] = ("error", msg)
            else:
                st.session_state["ws_push_flash"] = ("ok", msg)
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    if push:
        _run_push(only_failed=False)
    if retry:
        _run_push(only_failed=True)

    flash = st.session_state.pop("ws_push_flash", None)
    if flash:
        kind, msg = flash
        if kind == "error":
            st.error(msg)
        else:
            st.success(msg)

    results = st.session_state.get("last_submit_results") or []
    if not results:
        return

    st.markdown("#### Kết quả lần đẩy gần nhất")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "row": r["row_no"],
                    "full_name": r["full_name"],
                    "status": r["status"],
                    "http": r["http_status"],
                    "error": r["error"],
                    "response": (r["response_body"] or "")[:220],
                }
                for r in results
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Response đầy đủ"):
        for r in results:
            st.markdown(
                f"**#{r['row_no']} {r['full_name']}** — `{r['status']}` "
                f"(HTTP {r['http_status']})"
            )
            if r["error"]:
                st.error(r["error"])
            st.code(r["response_body"] or "(empty)", language="text")


@st.fragment
def _render_candidates_grid() -> None:
    """Lưới chỉnh sửa — fragment để sửa ô không remount cả trang / nhảy về đầu."""
    draft: list[dict] = list(st.session_state.draft_candidates or [])
    edited_df = st.data_editor(
        _draft_to_dataframe(draft),
        use_container_width=True,
        num_rows="dynamic",
        hide_index=False,
        height=380,
        column_config={
            "Submitted": st.column_config.TextColumn(
                "Submitted",
                help="✓ = SĐT đã từng đẩy thành công (giữ khi xóa batch)",
                width="small",
                disabled=True,
            ),
            "SubmitStatus": st.column_config.TextColumn(
                "Push",
                help="pending · success · failed — lưu cùng batch, không sửa tay",
                width="small",
                disabled=True,
            ),
            "SubmitError": st.column_config.TextColumn(
                "Lỗi push",
                help="Chi tiết lỗi lần đẩy gần nhất (sửa dữ liệu rồi Đẩy lại dòng lỗi)",
                width="medium",
                disabled=True,
            ),
            "AddressIcon": st.column_config.TextColumn(
                "★",
                help="✓ đủ · … một phần · ★ gợi ý mới · ? chưa nhận ra",
                width="small",
            ),
            "FullName": st.column_config.TextColumn("Họ tên", required=True),
            "Mobile": st.column_config.TextColumn("SĐT", width="small"),
            "FullAddress": st.column_config.TextColumn(
                "Địa chỉ (1 dòng)",
                help="Nhập địa chỉ thuần; bấm «Quét lại từ FullAddress» để tách Prov/Dist/Ward",
                width="large",
            ),
            "AddrTmpStreet": st.column_config.TextColumn("Đường", width="small"),
            "AddrTmpProvince": st.column_config.TextColumn("Tỉnh"),
            "AddrTmpDistrict": st.column_config.TextColumn("TP/Quận"),
            "AddrTmpWard": st.column_config.TextColumn("Phường"),
            "AddressNote": st.column_config.TextColumn("Ghi chú ĐC", width="medium"),
            "Sex": st.column_config.TextColumn("Sex", help="1 Nam · 2 Nữ", width="small"),
            "Birthday": st.column_config.TextColumn("NS", width="small"),
            "AcademicLevel": st.column_config.TextColumn("Học vấn"),
            "Email": st.column_config.TextColumn("Email"),
            "Height": st.column_config.TextColumn("Cao", width="small"),
            "Weight": st.column_config.TextColumn("Nặng", width="small"),
            "ApplyExperienceNote": st.column_config.TextColumn("Kinh nghiệm"),
            "WishWorkplace": st.column_config.TextColumn("Wish"),
            "ProjectHeadcountType": st.column_config.TextColumn("Type", width="small"),
        },
        key=_EDITOR_KEY,
    )
    # Chỉ cache working rows — không ghi đè draft_candidates (tránh reset lưới)
    st.session_state.grid_working_rows = _rows_from_editor(
        edited_df, draft, auto_enrich=False
    )


def _render_edit_screen() -> None:
    draft: list[dict] = st.session_state.draft_candidates
    batch_id = st.session_state.draft_batch_id
    filename = st.session_state.draft_filename or "upload"

    saved = batch_id is not None
    status_chip = f"batch #{batch_id}" if saved else "chưa lưu"
    st.markdown(f"### Đang làm việc · `{filename}` · {status_chip} · **{len(draft)}** dòng")

    top_l, top_mid, top_r = st.columns([2, 1, 1])
    with top_mid:
        if saved and st.button("Xóa batch này", use_container_width=True):
            _delete_batch_modal(int(batch_id), filename, len(draft))
    with top_r:
        if st.button("← Về danh sách", use_container_width=True):
            _close_draft()
            st.rerun()

    flash = st.session_state.pop("ws_delete_flash", None)
    if flash:
        st.success(flash)
    addr_flash = st.session_state.pop("ws_addr_flash", None)
    if addr_flash:
        st.success(addr_flash)

    if not saved:
        st.caption("File mới — có thể **Lưu** hoặc chọn dự án rồi **Đẩy** (tự lưu).")
    st.caption(
        "Gõ/dán trực tiếp trên lưới — dữ liệu giữ nguyên khi sửa. "
        "Sau khi sửa FullAddress, bấm **Quét lại từ FullAddress** để tách tỉnh/huyện/xã."
    )

    _render_candidates_grid()
    working_rows = _get_editor_working_rows(auto_enrich=False)
    if not working_rows:
        st.warning("Lưới trống — thêm ít nhất 1 dòng.")
        return

    working_rows = _render_address_panel(working_rows)

    save_l, save_r = st.columns([2, 1])
    with save_l:
        save_label = (
            f"Lưu cập nhật batch #{batch_id}"
            if saved
            else "Lưu thành batch mới"
        )
        if st.button(save_label, type="primary", use_container_width=True):
            try:
                rows = _get_editor_working_rows(auto_enrich=False)
                new_id = _persist_working_rows(
                    rows,
                    batch_id=batch_id,
                    filename=filename or "manual.xlsx",
                )
                st.success(f"Đã lưu batch #{new_id} — {len(rows)} ứng viên.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    with save_r:
        if st.button("Xóa draft (không lưu)", use_container_width=True):
            _close_draft()
            st.rerun()

    st.divider()
    rows_for_push = _get_editor_working_rows(auto_enrich=False)
    _render_push_panel(
        int(batch_id) if batch_id is not None else 0,
        len(rows_for_push),
        working_rows=rows_for_push,
        filename=filename or "manual.xlsx",
    )


def render_candidates_workspace() -> None:
    _ensure_state()
    st.subheader("Ứng viên")
    st.caption(
        "Import Excel (FullAddress 1 dòng) → app tách địa chỉ · "
        "★ = địa chỉ mới cần xác nhận map → lưu → chọn dự án & đẩy. "
        "Apply URL lấy từ **Link Apply** của project (tab Projects). "
        "Cột Submitted = SĐT đã từng đẩy thành công (giữ khi xóa batch)."
    )

    batches = list_import_batches()
    draft = st.session_state.draft_candidates
    in_edit = bool(draft) or st.session_state.ws_mode == "edit"

    if in_edit and draft:
        _render_edit_screen()
    else:
        st.session_state.ws_mode = "pick"
        _render_pick_screen(batches)
