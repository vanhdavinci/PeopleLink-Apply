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
from app.services.project_sync import mark_expired_projects, sync_projects
from app.services.user_service import (
    ensure_app_user,
    list_user_projects,
    update_app_user_fields,
)
from app.services.ward_mapping import import_ward_mapping_csv, mapping_stats
from app.services.welcome_gate import is_unlocked
from app.ui.candidates import render_candidates_workspace
from app.ui.theme import bootstrap_theme, render_app_header, render_setup_user_card
from app.ui.welcome import render_welcome_gate

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🌸",
    layout="wide",
)

bootstrap_theme()

with st.spinner("Khởi tạo database..."):
    db_path = init_db()

# —— Màn chào / mở khóa ——
if not is_unlocked():
    st.markdown(
        f"""
<div style="text-align:center;margin:0.5rem 0 0.25rem 0">
  <h1 class="pl-brand-title" style="font-size:1.65rem !important">{APP_NAME}</h1>
  <p class="pl-brand-sub">v{APP_VERSION} · local 🌸</p>
</div>
        """,
        unsafe_allow_html=True,
    )
    render_welcome_gate()
    st.stop()

# —— App chính (đã mở khóa) ——
render_app_header(app_name=APP_NAME, version=APP_VERSION)

stats = db_stats()
app_user = ensure_app_user()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Provinces", stats["provinces"])
m2.metric("Districts", stats["districts"])
m3.metric("Wards", stats["wards"])
m4.metric("Projects", stats["projects"])
m5.metric("Candidates", stats.get("candidates", 0))

if "portal_cookie" not in st.session_state:
    st.session_state.portal_cookie = ""

with st.expander("Portal cookie (chỉ dùng cho Sync Projects)", expanded=False):
    st.text_area(
        "Cookie",
        height=72,
        placeholder="ASP.NET_SessionId=...; _ga=...",
        key="portal_cookie",
        label_visibility="collapsed",
    )
    st.caption("Chỉ cần khi Sync Projects — đẩy apply không cần cookie.")

tab_work, tab_setup = st.tabs(["Ứng viên", "Thiết lập"])

with tab_work:
    render_candidates_workspace()

with tab_setup:
    render_setup_user_card(app_user)
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
    st.subheader("Sync Projects")
    st.caption("Dùng cookie ở expander phía trên → Sync Projects.")

    col_a, col_b = st.columns(2)
    with col_a:
        sync_clicked = st.button("Sync Projects", type="primary", use_container_width=True)
    with col_b:
        expire_clicked = st.button(
            "Đánh dấu project hết hạn", use_container_width=True
        )

    if sync_clicked:
        cookie = (st.session_state.get("portal_cookie") or "").strip()
        if not cookie:
            st.error("Dán portal cookie ở expander phía trên trước.")
        else:
            try:
                with st.spinner("Đang sync projects..."):
                    result = sync_projects(cookie=cookie, save_cookie=False)
                st.success(
                    f"OK — projects={result.project_count}, "
                    f"members={result.member_count}, "
                    f"mới hết hạn={result.expired_count}"
                )
                if result.errors:
                    st.warning("\n".join(result.errors[:10]))
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    if expire_clicked:
        result = mark_expired_projects()
        st.info(
            f"Đã đánh dấu hết hạn: {result.expired_count} · "
            f"gỡ hết hạn: {result.unexpired_count} · "
            f"tổng expired hiện tại: {result.project_count}"
        )
        st.rerun()

    user_projects = list_user_projects()
    st.write(f"Projects gắn user: **{len(user_projects)}**")
    if user_projects:
        st.dataframe(user_projects, use_container_width=True, hide_index=True)

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
