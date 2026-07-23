"""Soft pink dreamy theme + avatar chrome for Streamlit UI."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from app.config import ROOT_DIR
from app.services.user_service import APP_USER_FIRST_NAME, APP_USER_FULL_NAME

PICTURES_DIR = ROOT_DIR / "pictures"
BACKGROUND_PATH = PICTURES_DIR / "background.jpg"
AVATAR_PATH = PICTURES_DIR / "avatar.jpg"


def _data_uri(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".") or "jpeg"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def apply_dreamy_theme() -> None:
    """Inject soft-pink dreamy CSS + background image."""
    bg_uri = _data_uri(BACKGROUND_PATH) if BACKGROUND_PATH.is_file() else ""
    bg_rule = (
        f'url("{bg_uri}") center center / cover no-repeat fixed'
        if bg_uri
        else "linear-gradient(180deg, #fff5f8 0%, #ffe8f0 45%, #ffd6e7 100%)"
    )

    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=Playfair+Display:wght@500;600;700&display=swap');

:root {{
  --pl-rose: #e891b0;
  --pl-rose-deep: #d46a92;
  --pl-rose-soft: #f7c5d8;
  --pl-blush: #fff0f5;
  --pl-ink: #5c3a4a;
  --pl-muted: #8a6574;
  --pl-glass: rgba(255, 250, 252, 0.78);
  --pl-glass-strong: rgba(255, 255, 255, 0.90);
  --pl-border: rgba(232, 145, 176, 0.35);
  --pl-shadow: 0 10px 40px rgba(212, 106, 146, 0.12);
}}

html, body, [data-testid="stAppViewContainer"] {{
  font-family: "Nunito", "Segoe UI", sans-serif;
  color: var(--pl-ink);
}}

[data-testid="stAppViewContainer"] {{
  background: {bg_rule};
}}

/* Ẩn thanh navbar mờ phía trên của Streamlit */
header[data-testid="stHeader"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
#MainMenu {{
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
}}

.stApp > header {{
  display: none !important;
}}

.block-container {{
  padding-top: 1.4rem !important;
  padding-bottom: 2.5rem !important;
  max-width: 1180px;
}}

div[data-testid="stMetric"],
div[data-testid="stExpander"],
[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {{
  background: var(--pl-glass) !important;
  border: 1px solid var(--pl-border) !important;
  border-radius: 18px !important;
  box-shadow: var(--pl-shadow);
  backdrop-filter: blur(12px);
}}

div[data-testid="stMetric"] {{
  padding: 0.65rem 0.9rem;
}}

div[data-testid="stMetric"] label {{
  color: var(--pl-muted) !important;
}}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
  color: var(--pl-rose-deep) !important;
  font-family: "Playfair Display", Georgia, serif;
}}

h1, h2, h3, .pl-brand-title {{
  font-family: "Playfair Display", Georgia, serif !important;
  color: var(--pl-rose-deep) !important;
  letter-spacing: 0.01em;
}}

.stCaption, [data-testid="stCaptionContainer"] {{
  color: var(--pl-muted) !important;
}}

button[data-baseweb="tab"] {{
  font-family: "Nunito", sans-serif !important;
  font-weight: 700 !important;
  color: var(--pl-muted) !important;
}}

button[data-baseweb="tab"][aria-selected="true"] {{
  color: var(--pl-rose-deep) !important;
}}

[data-baseweb="tab-highlight"] {{
  background-color: var(--pl-rose) !important;
}}

.stButton > button {{
  border-radius: 999px !important;
  border: 1px solid var(--pl-rose-soft) !important;
  font-weight: 700 !important;
  font-family: "Nunito", sans-serif !important;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}}

.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {{
  background: linear-gradient(135deg, #f0a0be 0%, #e27aa5 100%) !important;
  color: white !important;
  border: none !important;
  box-shadow: 0 8px 20px rgba(226, 122, 165, 0.35);
}}

.stButton > button:hover {{
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(226, 122, 165, 0.28);
}}

.stTextInput input, .stTextArea textarea,
.stSelectbox [data-baseweb="select"] > div {{
  border-radius: 14px !important;
  border-color: var(--pl-border) !important;
  background: var(--pl-glass-strong) !important;
}}

.stTextInput input:focus, .stTextArea textarea:focus {{
  border-color: var(--pl-rose) !important;
  box-shadow: 0 0 0 3px rgba(232, 145, 176, 0.25) !important;
}}

div[data-testid="stTabs"] {{
  background: var(--pl-glass);
  border: 1px solid var(--pl-border);
  border-radius: 20px;
  padding: 1rem 1.25rem 2rem;
  box-shadow: var(--pl-shadow);
  backdrop-filter: blur(12px);
}}

div[data-testid="stAlert"] {{
  border-radius: 14px !important;
  border: 1px solid var(--pl-border) !important;
  background: rgba(255, 250, 252, 0.9) !important;
}}

hr {{
  border-color: rgba(232, 145, 176, 0.25) !important;
}}

footer {{
  visibility: hidden;
}}

/* Hàng header */
div.st-key-pl_header_row {{
  margin-bottom: 1rem !important;
}}

div[data-testid="stHorizontalBlock"]:has(.pl-header-card) {{
  align-items: center !important;
}}

/* Cả 2 thẻ — HTML flex, căn giữa dọc */
.pl-header-card {{
  position: relative;
  height: 104px;
  min-height: 104px;
  max-height: 104px;
  padding: 0 1.2rem;
  background: var(--pl-glass);
  border: 1px solid var(--pl-border);
  border-radius: 22px;
  box-shadow: var(--pl-shadow);
  backdrop-filter: blur(14px);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  width: 100%;
  gap: 0.75rem;
}}

.pl-brand-card .pl-brand-inner {{
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.2rem;
  width: 100%;
  margin: 0;
  padding: 0;
}}

.pl-brand-title {{
  margin: 0 !important;
  padding: 0 !important;
  font-size: 1.48rem !important;
  line-height: 1.2 !important;
  font-family: "Playfair Display", Georgia, serif !important;
  color: var(--pl-rose-deep) !important;
}}

.pl-brand-sub {{
  margin: 0 !important;
  padding: 0 !important;
  color: var(--pl-muted);
  font-size: 0.84rem;
  line-height: 1.3;
}}

/* User card phải — chừa chỗ nút ⚙ absolute */
.pl-user-card-html {{
  padding-right: 3.6rem;
}}

.pl-user-card-html .pl-user-meta {{
  display: flex;
  flex-direction: column;
  justify-content: center;
  line-height: 1.25;
  text-align: left;
  flex: 1;
  min-width: 0;
}}

.pl-user-name {{
  font-weight: 800;
  color: var(--pl-rose-deep);
  font-size: 0.98rem;
}}

.pl-user-hint {{
  font-size: 0.74rem;
  color: var(--pl-muted);
  margin-top: 0.1rem;
}}

/* Cột phải: đặt nút ⚙ Streamlit đúng chỗ bánh răng */
div[data-testid="stColumn"]:has(.pl-user-card-html) {{
  position: relative !important;
}}

div[data-testid="stColumn"]:has(.pl-user-card-html) div.st-key-pl_open_avatar {{
  position: absolute !important;
  right: 1.15rem;
  top: 31px; /* (104px - 42px) / 2 */
  z-index: 6;
  width: 42px !important;
  height: 0 !important;
  margin: 0 !important;
  overflow: visible !important;
}}

div.st-key-pl_open_avatar .stButton {{
  height: 42px !important;
}}

div.st-key-pl_open_avatar .stButton > button,
div.st-key-pl_open_avatar_setup .stButton > button {{
  width: 42px !important;
  height: 42px !important;
  min-width: 42px !important;
  max-width: 42px !important;
  padding: 0 !important;
  margin: 0 !important;
  border-radius: 50% !important;
  border: 1.5px solid var(--pl-rose-soft) !important;
  background: rgba(255, 255, 255, 0.88) !important;
  box-shadow: 0 4px 12px rgba(212, 106, 146, 0.2) !important;
  color: var(--pl-rose-deep) !important;
  font-size: 1.15rem !important;
  line-height: 1 !important;
}}

div.st-key-pl_open_avatar .stButton > button:hover,
div.st-key-pl_open_avatar_setup .stButton > button:hover {{
  transform: rotate(25deg) scale(1.06) !important;
  background: #fff0f5 !important;
}}

/* Avatar ảnh tĩnh */
img.pl-avatar-static {{
  display: block;
  width: 52px;
  height: 52px;
  object-fit: cover;
  border-radius: 50%;
  border: 3px solid #ffffff;
  box-shadow: 0 4px 14px rgba(212, 106, 146, 0.32);
  background: #fff0f5;
  flex-shrink: 0;
}}

img.pl-avatar-static-lg {{
  width: 140px;
  height: 140px;
  margin: 0 auto;
}}

.pl-setup-avatar-wrap {{
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  padding: 0.35rem 0 0.5rem 0;
}}

.pl-setup-avatar-wrap img.pl-avatar-static {{
  width: 140px;
  height: 140px;
}}

div.pl-avatar-dialog [data-testid="stImage"] img {{
  border-radius: 22px;
  box-shadow: 0 16px 40px rgba(92, 58, 74, 0.22);
  border: 3px solid rgba(255, 255, 255, 0.95);
}}

.pl-avatar-dialog-title {{
  text-align: center;
  margin-top: 0.6rem;
  font-family: "Playfair Display", Georgia, serif;
  color: var(--pl-rose-deep);
  font-size: 1.35rem;
  font-weight: 600;
}}

.pl-avatar-dialog-sub {{
  text-align: center;
  color: var(--pl-muted);
  margin-top: -0.2rem;
  margin-bottom: 0.6rem;
}}

/* Address panel: 2 khối cùng style, chỉ khác badge + khoảng cách */
.pl-addr-head {{
  margin: 0 0 0.85rem 0;
  padding: 0 0 0.85rem 0;
  border-bottom: 1px solid rgba(232, 145, 176, 0.28);
}}

.pl-addr-kicker {{
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #fff;
  background: var(--pl-rose);
  padding: 0.22rem 0.65rem;
  border-radius: 999px;
  margin-bottom: 0.45rem;
}}

.pl-addr-kicker--1 {{
  background: linear-gradient(135deg, #f0a0be, #e27aa5);
}}

.pl-addr-kicker--2 {{
  background: linear-gradient(135deg, #d46a92, #c25580);
}}

.pl-addr-title {{
  margin: 0 0 0.35rem 0 !important;
  font-size: 1.28rem !important;
  font-family: "Playfair Display", Georgia, serif !important;
  color: var(--pl-rose-deep) !important;
  line-height: 1.25 !important;
}}

.pl-addr-desc {{
  margin: 0;
  font-size: 0.98rem;
  line-height: 1.45;
  color: var(--pl-ink);
  opacity: 0.9;
}}

.pl-addr-gap {{
  height: 1.75rem;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


@st.dialog("✨ Hồ sơ")
def open_avatar_dialog() -> None:
    st.markdown('<div class="pl-avatar-dialog">', unsafe_allow_html=True)
    if AVATAR_PATH.is_file():
        st.image(str(AVATAR_PATH), use_container_width=True)
    else:
        st.warning("Chưa có `pictures/avatar.jpg`.")
    st.markdown(
        f'<div class="pl-avatar-dialog-title">{APP_USER_FULL_NAME}</div>'
        f'<div class="pl-avatar-dialog-sub">Recruiter · PeopleLink Apply</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("Đóng", use_container_width=True, type="primary"):
        st.rerun()


def _render_avatar_image(*, size: str = "sm", centered: bool = False) -> None:
    """Ảnh avatar tròn — chỉ hiển thị, không bấm."""
    cls = "pl-avatar-static pl-avatar-static-lg" if size == "lg" else "pl-avatar-static"
    if AVATAR_PATH.is_file():
        uri = _data_uri(AVATAR_PATH)
        inner = f'<img class="{cls}" src="{uri}" alt="{APP_USER_FULL_NAME}" />'
    else:
        dim = "140px" if size == "lg" else "56px"
        inner = (
            f'<div class="{cls}" style="display:flex;align-items:center;'
            f'justify-content:center;font-size:1.4rem;background:#ffe8f0;'
            f'width:{dim};height:{dim};border-radius:50%">👤</div>'
        )
    if centered:
        st.markdown(
            f'<div class="pl-setup-avatar-wrap">{inner}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(inner, unsafe_allow_html=True)


@st.fragment
def _render_settings_button(*, key: str) -> None:
    """Nút răng cưa — mở modal hồ sơ / avatar."""
    if st.button(
        "⚙",
        key=key,
        help=f"Cài đặt / xem hồ sơ · {APP_USER_FULL_NAME}",
    ):
        open_avatar_dialog()


def _render_header_settings_button() -> None:
    """Nút ⚙ trong header (không dùng fragment để giữ chiều cao thẻ)."""
    if st.button(
        "⚙",
        key="pl_open_avatar",
        help=f"Cài đặt / xem hồ sơ · {APP_USER_FULL_NAME}",
    ):
        open_avatar_dialog()


def render_app_header(*, app_name: str, version: str) -> None:
    """Hai thẻ header HTML cùng style: căn giữa dọc, cao bằng nhau."""
    avatar_uri = _data_uri(AVATAR_PATH) if AVATAR_PATH.is_file() else ""
    if avatar_uri:
        avatar_html = (
            f'<img class="pl-avatar-static" src="{avatar_uri}" '
            f'alt="{APP_USER_FULL_NAME}" />'
        )
    else:
        avatar_html = (
            '<div class="pl-avatar-static" style="display:flex;align-items:center;'
            'justify-content:center;font-size:1.4rem;background:#ffe8f0">👤</div>'
        )

    with st.container(key="pl_header_row"):
        left, right = st.columns(
            [2.15, 1.35], gap="medium", vertical_alignment="center"
        )

        with left:
            st.markdown(
                f"""
<div class="pl-header-card pl-brand-card">
  <div class="pl-brand-inner">
    <h1 class="pl-brand-title">{app_name}</h1>
    <p class="pl-brand-sub">v{version} · for VA's "cục dàng" {APP_USER_FIRST_NAME} 🌸</p>
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )

        with right:
            st.markdown(
                f"""
<div class="pl-header-card pl-user-card-html">
  {avatar_html}
  <div class="pl-user-meta">
    <span class="pl-user-name">{APP_USER_FULL_NAME}</span>
    <span class="pl-user-hint">Nhấn ⚙ để xem hồ sơ</span>
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )
            # Một nút ⚙ duy nhất (key=pl_open_avatar) — mở modal hồ sơ
            _render_header_settings_button()


def render_setup_user_card(app_user: dict) -> None:
    """User block in Thiết lập — avatar lớn căn giữa, không nút cài đặt."""
    c1, c2 = st.columns([1.1, 2.9], vertical_alignment="center")
    with c1:
        _render_avatar_image(size="lg", centered=True)
    with c2:
        st.subheader("User")
        st.caption(
            f"App dùng cho **{APP_USER_FULL_NAME}** — "
            "RecruiterPIC / HeadcountRequestID dùng khi đẩy apply."
        )
        st.write(
            f"RecruiterPIC hiện tại: `{app_user.get('recruiter_pic') or '—'}` · "
            f"HeadcountRequestID: `{app_user.get('headcount_request_id') or '—'}`"
        )


def bootstrap_theme() -> None:
    apply_dreamy_theme()
