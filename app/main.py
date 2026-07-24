from __future__ import annotations

import sys
from pathlib import Path

# Allow `streamlit run app/main.py` from project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.config import APP_NAME, APP_VERSION
from app.db import db_stats, init_db
from app.services.location_sync import sync_locations
from app.services.user_service import (
    ensure_app_user,
    update_app_user_fields,
)
from app.services.ward_mapping import import_ward_mapping_csv, mapping_stats
from app.services.auth import (
    current_username,
    is_authenticated,
    logout,
    session_expires_in_seconds,
)
from app.ui.candidates import render_candidates_workspace
from app.ui.projects import render_projects_workspace
from app.ui.theme import bootstrap_theme, render_app_header, render_setup_user_card
from app.ui.welcome import render_login_gate

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🌸",
    layout="wide",
)

bootstrap_theme()

with st.spinner("Khởi tạo database..."):
    db_path = init_db()

# —— Đăng nhập ——
if not is_authenticated():
    st.markdown(
        f"""
<div style="text-align:center;margin:0.5rem 0 0.25rem 0">
  <h1 class="pl-brand-title" style="font-size:1.65rem !important">{APP_NAME}</h1>
  <p class="pl-brand-sub">v{APP_VERSION} · local 🌸</p>
</div>
        """,
        unsafe_allow_html=True,
    )
    render_login_gate()
    st.stop()

# —— App chính (đã đăng nhập) ——
render_app_header(app_name=APP_NAME, version=APP_VERSION)

stats = db_stats()
app_user = ensure_app_user()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Provinces", stats["provinces"])
m2.metric("Districts", stats["districts"])
m3.metric("Wards", stats["wards"])
m4.metric("Projects", stats["projects"])
m5.metric("Candidates", stats.get("candidates", 0))

tab_work, tab_projects, tab_setup = st.tabs(
    ["Ứng viên", "Projects", "Thiết lập"]
)

with tab_work:
    render_candidates_workspace()

with tab_projects:
    render_projects_workspace()

with tab_setup:
    render_setup_user_card(app_user)
    remaining = session_expires_in_seconds()
    who = current_username()
    if who:
        st.caption(f"Đăng nhập: **{who}**")
    if remaining is not None:
        mins = remaining // 60
        st.caption(f"Phiên còn khoảng **{mins} phút** (tự gia hạn khi còn dùng app).")
    if st.button("Đăng xuất", key="btn_logout"):
        logout()
        st.rerun()
    with st.form("user_fields_form"):
        col_u1, col_u2 = st.columns(2)
        with col_u1:
            recruiter_pic = st.text_input(
                "RecruiterPIC",
                value=app_user.get("recruiter_pic") or "",
                placeholder="28924",
            )
        with col_u2:
            headcount_request_id = st.text_input(
                "HeadcountRequestID",
                value=app_user.get("headcount_request_id") or "",
                placeholder="1823",
            )
        saved = st.form_submit_button("Lưu User", type="primary")
    if saved:
        updated = update_app_user_fields(
            recruiter_pic=recruiter_pic,
            headcount_request_id=headcount_request_id,
        )
        st.success(
            f"Đã lưu — RecruiterPIC={updated.get('recruiter_pic')!r}, "
            f"HeadcountRequestID={updated.get('headcount_request_id')!r}"
        )
        st.rerun()

    st.divider()
    st.subheader("Sync địa chỉ (Province → District → Ward)")
    st.caption(
        "Kéo huyện/phường từ Location API vào SQLite — dùng cho dropdown địa chỉ. "
        "Tự xóa mã sai (QUYNHON) + mã số trước khi sync. Có thể mất vài phút."
    )
    loc_stats = db_stats()
    l1, l2, l3 = st.columns(3)
    l1.metric("Provinces", loc_stats["provinces"])
    l2.metric("Districts", loc_stats["districts"])
    l3.metric("Wards", loc_stats["wards"])

    sync_loc = st.button(
        "Sync Locations (Prov / Dist / Ward)",
        type="primary",
        use_container_width=True,
        key="btn_sync_locations",
    )
    if sync_loc:
        if int(loc_stats.get("provinces") or 0) <= 0:
            st.error(
                "Chưa có bảng provinces trong DB — cần seed province trước "
                "(file provincedata / sync tỉnh)."
            )
        else:
            log = st.empty()
            try:
                with st.spinner("Đang sync districts + wards..."):
                    result = sync_locations(
                        letter_codes_only=True,
                        sync_wards=True,
                        progress=lambda msg: log.write(msg),
                    )
                st.success(
                    f"OK — provinces={result.province_count}, "
                    f"districts={result.district_count}, "
                    f"wards={result.ward_count}"
                )
                if result.errors:
                    st.warning("\n".join(result.errors[:15]))
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    st.divider()
    st.subheader("Mapping địa chỉ (cũ ↔ mới)")
    st.caption(
        "CSV `ward_mapping_old_to_new.csv` — portal chỉ nhận địa chỉ cũ "
        "(tỉnh/huyện/xã). Batch có thể nhập địa chỉ mới; mapping dùng để quy đổi sau."
    )
    wstats = mapping_stats()
    w1, w2, w3, w4 = st.columns(4)
    w1.metric("Tổng dòng", wstats["total"])
    w2.metric("MAPPED", wstats["mapped"])
    w3.metric("DIVIDED", wstats["divided"])
    w4.metric("NOT_FOUND", wstats["not_found"])
    if st.button("Import / cập nhật mapping từ CSV", type="primary"):
        try:
            with st.spinner("Đang import ward mapping..."):
                result = import_ward_mapping_csv()
            st.success(
                f"OK — {result.inserted} dòng "
                f"(MAPPED={result.mapped}, DIVIDED={result.divided}, "
                f"NOT_FOUND={result.not_found})"
            )
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    with st.expander("DB / đường dẫn"):
        st.write(f"SQLite: `{db_path}`")
        st.json(db_stats())
