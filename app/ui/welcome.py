"""Màn chào mừng / mở khóa app — cùng theme hồng mộng mơ."""
from __future__ import annotations

import random
from datetime import date, timedelta

import streamlit as st

from app.services.welcome_gate import (
    EXPECTED_LOVE_DATE,
    get_saved_gate,
    save_gate_attempt,
)
from app.services.user_service import APP_USER_FIRST_NAME


def _random_decoy_date() -> date:
    """Ngày giả ngẫu nhiên — không trùng ngày đúng."""
    for _ in range(40):
        year = random.randint(2018, 2027)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        decoy = date(year, month, day)
        if decoy != EXPECTED_LOVE_DATE:
            return decoy
    return EXPECTED_LOVE_DATE - timedelta(days=17)


def render_welcome_gate() -> bool:
    """
    Hiện màn chào. Trả về True nếu đã mở khóa (được vào app chính).
    """
    saved = get_saved_gate()
    if saved["is_unlocked"]:
        return True

    st.markdown(
        f"""
<style>
.pl-welcome-wrap {{
  max-width: 520px;
  margin: 2.5rem auto 2rem auto;
}}
.pl-welcome-card {{
  background: var(--pl-glass, rgba(255,250,252,0.82));
  border: 1px solid var(--pl-border, rgba(232,145,176,0.35));
  border-radius: 24px;
  box-shadow: var(--pl-shadow, 0 10px 40px rgba(212,106,146,0.12));
  backdrop-filter: blur(14px);
  padding: 1.75rem 1.6rem 1.5rem;
  text-align: center;
}}
.pl-welcome-kicker {{
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fff;
  background: linear-gradient(135deg, #f0a0be, #e27aa5);
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  margin-bottom: 0.85rem;
}}
.pl-welcome-title {{
  margin: 0 0 0.55rem 0 !important;
  font-family: "Playfair Display", Georgia, serif !important;
  color: var(--pl-rose-deep, #d46a92) !important;
  font-size: 1.75rem !important;
  line-height: 1.25 !important;
}}
.pl-welcome-sub {{
  margin: 0 0 1.35rem 0;
  color: var(--pl-ink, #5c3a4a);
  font-size: 1.02rem;
  line-height: 1.5;
  opacity: 0.92;
}}
.pl-welcome-hint {{
  margin-top: 0.85rem;
  font-size: 0.82rem;
  color: var(--pl-muted, #8a6574);
}}
</style>
<div class="pl-welcome-wrap">
  <div class="pl-welcome-card">
    <span class="pl-welcome-kicker">Welcome · {APP_USER_FIRST_NAME} 🌸</span>
    <h1 class="pl-welcome-title">Queo com cục dàng mét gữi</h1>
    <p class="pl-welcome-sub">
      Vui lòng nhập số điện thoại anh iu và ngày em nhận lời iu anh để vào app
    </p>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    default_phone = saved["phone"] or ""
    # Ngày mặc định random — không prefill đáp án đúng
    if "welcome_decoy_date" not in st.session_state:
        st.session_state.welcome_decoy_date = _random_decoy_date()
    default_date = st.session_state.welcome_decoy_date

    with st.container():
        _c1, c2, _c3 = st.columns([1, 1.35, 1])
        with c2:
            with st.form("welcome_gate_form", clear_on_submit=False):
                phone = st.text_input(
                    "Số điện thoại anh iu",
                    value=default_phone,
                    placeholder="0xxx xxx xxx",
                    help="Nhập số điện thoại (10 số)",
                )
                love_day = st.date_input(
                    "Ngày em nhận lời iu anh",
                    value=default_date,
                    format="DD/MM/YYYY",
                    min_value=date(2000, 1, 1),
                    max_value=date(2099, 12, 31),
                )
                submitted = st.form_submit_button(
                    "Vào app 💕",
                    type="primary",
                    use_container_width=True,
                )

            if submitted:
                result = save_gate_attempt(phone=phone, love_date=love_day)
                if result["ok"]:
                    st.session_state.pop("welcome_decoy_date", None)
                    st.success("Đúng rồi cục dàng 🌸 — đang vào app...")
                    st.balloons()
                    st.rerun()
                else:
                    st.session_state.welcome_decoy_date = love_day
                    st.error(
                        "Chưa đúng số điện thoại hoặc ngày nhận lời iu — "
                        "thử lại nha 💗"
                    )

            st.markdown(
                '<p class="pl-welcome-hint" style="text-align:center">'
                "Hai giá trị sẽ được lưu trong máy (SQLite) khi bạn nhập."
                "</p>",
                unsafe_allow_html=True,
            )

    return False
