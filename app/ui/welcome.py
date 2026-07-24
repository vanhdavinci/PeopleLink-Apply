"""Màn đăng nhập — bảo vệ app, cùng theme hồng mộng mơ."""
from __future__ import annotations

import streamlit as st

from app.services.auth import is_authenticated, login
from app.services.user_service import APP_USER_FIRST_NAME


def render_login_gate() -> bool:
    """
    Hiện màn đăng nhập. Trả về True nếu đã đăng nhập (được vào app chính).
    """
    if is_authenticated():
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
    <span class="pl-welcome-kicker">Login · {APP_USER_FIRST_NAME} 🌸</span>
    <h1 class="pl-welcome-title">Đăng nhập</h1>
    <p class="pl-welcome-sub">
      Nhập tài khoản và mật khẩu để vào app
    </p>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        _c1, c2, _c3 = st.columns([1, 1.35, 1])
        with c2:
            with st.form("login_gate_form", clear_on_submit=False):
                username = st.text_input(
                    "Tài khoản",
                    value="",
                    placeholder="Tên đăng nhập",
                    autocomplete="username",
                )
                password = st.text_input(
                    "Mật khẩu",
                    value="",
                    type="password",
                    placeholder="••••••••",
                    autocomplete="current-password",
                )
                submitted = st.form_submit_button(
                    "Đăng nhập",
                    type="primary",
                    use_container_width=True,
                )

            if submitted:
                result = login(username=username, password=password)
                if result["ok"]:
                    st.success("Đăng nhập thành công — đang vào app...")
                    st.rerun()
                else:
                    st.error("Sai tài khoản hoặc mật khẩu — thử lại nha")

            st.markdown(
                '<p class="pl-welcome-hint" style="text-align:center">'
                "Phiên đăng nhập có thời hạn (token ký ngắn hạn). "
                "Hết hạn hoặc đăng xuất sẽ cần đăng nhập lại."
                "</p>",
                unsafe_allow_html=True,
            )

    return False
