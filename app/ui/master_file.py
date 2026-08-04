"""Tab Master File — import hồ sơ xlsx → xuất DANH SÁCH + LỊCH LÀM VIỆC."""
from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from app.services.locations import list_provinces
from app.services.master_file import (
    DANH_SACH_COLUMNS,
    LICH_COLUMNS,
    apply_lich_bulk_fields,
    format_schedule_days,
    format_schedule_times,
    make_time_slot,
    process_master_upload,
    refresh_master_export,
)

_MONTH_OPTIONS = list(range(1, 13))
_DAY_OPTIONS = list(range(1, 32))
_YEAR_OPTIONS = list(range(date.today().year - 1, date.today().year + 4))


def _sanitize_project_name(name: str) -> str:
    text = re.sub(r"\s+", " ", (name or "").strip())
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    return text.strip(" .")


def _build_export_filename(*, export_date: date, project_name: str) -> str:
    date_part = export_date.strftime("%d%m%Y")
    project = _sanitize_project_name(project_name) or "DU AN"
    return f"{date_part} - {project}.xlsx"


def _province_labels() -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for row in list_provinces():
        name = str(row.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        labels.append(name)
    return labels


def _ensure_ll_state() -> None:
    if "master_ll_dates" not in st.session_state:
        st.session_state.master_ll_dates = []
    if "master_ll_custom_times" not in st.session_state:
        st.session_state.master_ll_custom_times = []


def _clear_ll_editor_state() -> None:
    for key in (
        "master_ll_dates",
        "master_ll_custom_times",
        "master_ll_address",
        "master_ll_pick_days",
        "master_ll_pick_month",
        "master_ll_pick_months",
        "master_ll_pick_year",
        "master_ll_time_start",
        "master_ll_time_end",
        "master_ll_custom_times_editor",
    ):
        st.session_state.pop(key, None)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def _build_dates_from_parts(
    *,
    days: list[int],
    months: list[int],
    year: int,
) -> list[date]:
    """Tổ hợp ngày × tháng trong 1 năm; bỏ ngày không hợp lệ (31/02...)."""
    out: list[date] = []
    for month in sorted(set(months)):
        max_day = _days_in_month(year, month)
        for day in sorted(set(days)):
            if 1 <= day <= max_day:
                out.append(date(year, month, day))
    return out


def _render_lich_bulk_panel(result: dict) -> None:
    """Panel Address / Day / Time — áp dụng cho toàn bộ dòng LỊCH LÀM VIỆC."""
    _ensure_ll_state()
    st.markdown("##### Áp dụng Address · Day · Time (toàn bộ dòng)")
    st.caption(
        "Day dạng `25,26/07/2026` · Time dạng `6h-11h, 16h-20h` — "
        "chọn xong bấm **Áp dụng cho tất cả dòng**."
    )

    provinces = _province_labels()
    address = st.selectbox(
        "Address (Province)",
        options=[""] + provinces,
        index=0,
        key="master_ll_address",
        help="Lấy từ bảng provinces trong DB",
    )

    st.markdown("**Day — Ngày / Tháng / Năm**")
    c_d, c_m, c_y = st.columns([2, 2, 1])
    with c_d:
        selected_days = st.multiselect(
            "Ngày",
            options=_DAY_OPTIONS,
            default=[],
            key="master_ll_pick_days",
            help="Có thể chọn nhiều ngày (vd 25, 26)",
        )
    with c_m:
        selected_month = st.selectbox(
            "Tháng",
            options=_MONTH_OPTIONS,
            index=date.today().month - 1,
            key="master_ll_pick_month",
        )
    with c_y:
        selected_year = st.selectbox(
            "Năm",
            options=_YEAR_OPTIONS,
            index=_YEAR_OPTIONS.index(date.today().year)
            if date.today().year in _YEAR_OPTIONS
            else 0,
            key="master_ll_pick_year",
        )

    st.session_state.master_ll_dates = _build_dates_from_parts(
        days=list(selected_days),
        months=[int(selected_month)] if selected_month else [],
        year=int(selected_year),
    )
    day_text = format_schedule_days(st.session_state.master_ll_dates)
    st.caption(f"Day xuất: `{day_text or '—'}`")

    st.markdown("**Time — tự nhập khung giờ**")
    c_t1, c_t2, c_t3 = st.columns([1, 1, 1])
    with c_t1:
        start_h = st.number_input(
            "Giờ bắt đầu",
            min_value=0,
            max_value=23,
            value=6,
            step=1,
            key="master_ll_time_start",
        )
    with c_t2:
        end_h = st.number_input(
            "Giờ kết thúc",
            min_value=0,
            max_value=24,
            value=11,
            step=1,
            key="master_ll_time_end",
        )
    with c_t3:
        st.write("")
        st.write("")
        if st.button("Thêm khung giờ", use_container_width=True, key="master_ll_add_time"):
            slot = make_time_slot(int(start_h), int(end_h))
            customs = list(st.session_state.master_ll_custom_times)
            if slot not in customs:
                customs.append(slot)
                st.session_state.master_ll_custom_times = customs
            st.session_state.pop("master_ll_custom_times_editor", None)
            st.rerun()

    custom_opts = list(st.session_state.master_ll_custom_times)
    kept_custom = st.multiselect(
        "Khung giờ đã thêm (bỏ tick để xóa)",
        options=custom_opts,
        default=custom_opts,
        key="master_ll_custom_times_editor",
    )
    st.session_state.master_ll_custom_times = [
        s for s in kept_custom if s in set(custom_opts)
    ]

    time_text = format_schedule_times(list(st.session_state.master_ll_custom_times))
    st.caption(f"Time xuất: `{time_text or '—'}`")

    apply = st.button(
        "Áp dụng cho tất cả dòng",
        type="primary",
        use_container_width=True,
        key="master_ll_apply_bulk",
    )
    if apply:
        if not address and not day_text and not time_text:
            st.warning("Chọn ít nhất Address, Day hoặc Time trước khi áp dụng.")
            return
        lich = apply_lich_bulk_fields(
            list(result.get("lich") or []),
            address=address if address else None,
            day=day_text if day_text else None,
            time=time_text if time_text else None,
        )
        updated = dict(result)
        updated["lich"] = lich
        st.session_state.master_file_result = refresh_master_export(updated)
        st.success(
            "Đã áp dụng"
            + (f" · Address=`{address}`" if address else "")
            + (f" · Day=`{day_text}`" if day_text else "")
            + (f" · Time=`{time_text}`" if time_text else "")
        )
        st.rerun()


def render_master_file_workspace() -> None:
    st.subheader("Master File")
    st.caption(
        "Upload file hồ sơ ứng tuyển (nhiều cột) → map về template "
        "**DANH SÁCH** + **LỊCH LÀM VIỆC**."
    )

    col_date, col_proj = st.columns([1, 2])
    with col_date:
        export_date = st.date_input(
            "Ngày (file name)",
            value=date.today(),
            format="DD/MM/YYYY",
            key="master_file_export_date",
        )
    with col_proj:
        project_name = st.text_input(
            "Tên dự án (file name)",
            value=st.session_state.get("master_file_project_name", ""),
            placeholder="VD: LLV&MTF DỰ ÁN DHG - BIPP",
            key="master_file_project_name",
        )

    out_name = _build_export_filename(
        export_date=export_date if isinstance(export_date, date) else date.today(),
        project_name=project_name,
    )
    st.caption(f"Tên file xuất: `{out_name}`")

    uploaded = st.file_uploader(
        "Chọn file .xlsx hồ sơ nguồn",
        type=["xlsx"],
        key="master_file_uploader",
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        run = st.button(
            "Map & tạo Master File",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
            key="master_file_run",
        )
    with col_b:
        if st.button("Xóa kết quả", use_container_width=True, key="master_file_clear"):
            for k in (
                "master_file_result",
                "master_file_error",
                "master_file_name",
            ):
                st.session_state.pop(k, None)
            _clear_ll_editor_state()
            st.rerun()

    if run and uploaded is not None:
        try:
            with st.spinner("Đang map cột và tạo file..."):
                result = process_master_upload(uploaded.getvalue())
            st.session_state.master_file_result = result
            st.session_state.master_file_name = uploaded.name
            st.session_state.pop("master_file_error", None)
            _clear_ll_editor_state()
        except Exception as exc:  # noqa: BLE001
            st.session_state.master_file_error = str(exc)
            st.session_state.pop("master_file_result", None)

    err = st.session_state.get("master_file_error")
    if err:
        st.error(err)

    result = st.session_state.get("master_file_result")
    if not result:
        st.info(
            "Cột DANH SÁCH lấy từ template LLV&MTF. "
            "Sheet LỊCH LÀM VIỆC: map hồ sơ + panel Address/Day/Time bên dưới preview."
        )
        with st.expander("Cột xuất DANH SÁCH"):
            st.write(", ".join(DANH_SACH_COLUMNS))
        return

    src_name = st.session_state.get("master_file_name") or "upload.xlsx"
    m1, m2 = st.columns(2)
    m1.metric("Dòng DANH SÁCH", result["row_count"])
    m2.metric("Dòng LỊCH LÀM VIỆC", result["lich_count"])

    can_download = bool(_sanitize_project_name(project_name))
    if not can_download:
        st.warning("Nhập **Tên dự án** trước khi tải file.")

    st.download_button(
        "Tải Excel (DANH SÁCH + LỊCH LÀM VIỆC)",
        data=result["xlsx_bytes"],
        file_name=out_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
        disabled=not can_download,
        key="master_file_download",
    )
    st.caption(f"Nguồn: `{src_name}` · Xuất: `{out_name}`")

    tab_ds, tab_ll = st.tabs(["Preview DANH SÁCH", "Preview LỊCH LÀM VIỆC"])
    with tab_ds:
        df_ds = pd.DataFrame(result["danh_sach"], columns=DANH_SACH_COLUMNS)
        st.dataframe(df_ds, use_container_width=True, hide_index=True)
    with tab_ll:
        df_ll = pd.DataFrame(result["lich"], columns=LICH_COLUMNS)
        st.dataframe(df_ll, use_container_width=True, hide_index=True)
        st.divider()
        _render_lich_bulk_panel(result)
