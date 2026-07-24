"""Màn đăng nhập — bảo vệ app, cùng theme hồng mộng mơ."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from app.config import ROOT_DIR
from app.services.auth import is_authenticated, login
from app.services.user_service import APP_USER_FIRST_NAME

_PICTURES = ROOT_DIR / "pictures"
# Mỗi bên 4 tấm (2 trên · 2 dưới): trái pic2–5, phải pic1 + pic6–8
_LEFT_PICS = ("pic2.jpg", "pic3.jpg", "pic4.jpg", "pic5.jpg")
_RIGHT_PICS = ("pic1.jpg", "pic6.jpg", "pic7.jpg", "pic8.jpg")


def _data_uri(path: Path) -> str | None:
    if not path.is_file():
        return None
    suffix = path.suffix.lower().lstrip(".") or "jpeg"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


@st.cache_data(show_spinner=False)
def _load_login_uris(names: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for name in names:
        uri = _data_uri(_PICTURES / name)
        if uri:
            out.append(uri)
    return out


def _frame_html(uri: str, slot: int, side: str) -> str:
    return f"""
<figure class="pl-login-frame pl-login-frame--{side}-s{slot}">
  <div class="pl-login-frame-inner">
    <img src="{uri}" alt="" />
  </div>
  <figcaption>· · ·</figcaption>
</figure>
    """


def _col_html(uris: list[str], side: str) -> str:
    if not uris:
        return ""
    frames = "".join(_frame_html(u, i, side) for i, u in enumerate(uris[:4]))
    return f'<div class="pl-login-col pl-login-col--{side}">{frames}</div>'


def _render_login_decor() -> None:
    """Khung ảnh trang trí 2 bên (mỗi bên 2×2) — chỉ màn đăng nhập."""
    left = _load_login_uris(_LEFT_PICS)
    right = _load_login_uris(_RIGHT_PICS)
    if not left and not right:
        return

    st.markdown(
        f"""
<style>
.pl-login-decor {{
  /* Form giữa ~34vw (tối đa 520px); 2 bên chia đều phần còn lại · scale 90% */
  --pl-login-center: min(34vw, 520px);
  --pl-login-edge: 1.2vw;
  --pl-login-gutter: 1.6vw;
  --pl-login-side: calc(
    ((100vw - var(--pl-login-center) - 2 * var(--pl-login-edge) - 2 * var(--pl-login-gutter)) / 2) * 0.9
  );
  pointer-events: none;
  z-index: 2;
}}
.pl-login-col {{
  position: fixed;
  top: 8vh;
  bottom: 7vh;
  width: var(--pl-login-side);
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 0.4vh 0.5vw;
  align-content: stretch;
}}
.pl-login-col--left {{
  left: var(--pl-login-edge);
}}
.pl-login-col--right {{
  right: var(--pl-login-edge);
  gap: 1.3vh 1.1vw;
}}
.pl-login-frame {{
  position: relative;
  margin: -3% -4%;
  height: auto;
  min-height: 0;
  padding: 2.2%;
  padding-bottom: 1%;
  background: #fff;
  border-radius: 0.4em 0.4em 1em 1em;
  box-shadow:
    0 1.2vh 2.8vh rgba(212, 106, 146, 0.22),
    0 1px 0 rgba(255, 255, 255, 0.9) inset;
  border: 1px solid rgba(232, 145, 176, 0.45);
  display: flex;
  flex-direction: column;
}}
.pl-login-col--right .pl-login-frame {{
  margin: -0.8% -1.2%;
}}
.pl-login-frame::before {{
  content: "";
  position: absolute;
  top: -1.1vh;
  left: 50%;
  width: 45%;
  height: 3.5vh;
  min-height: 24px;
  background: linear-gradient(
    180deg,
    rgba(255, 236, 244, 0.95) 0%,
    rgba(255, 214, 230, 0.88) 55%,
    rgba(247, 197, 216, 0.82) 100%
  );
  border: none;
  border-radius: 0;
  box-shadow: 0 2px 5px rgba(92, 58, 74, 0.1);
  z-index: 2;
  /* Răng cưa 2 đầu kiểu keo washi */
  clip-path: polygon(
    2.2% 0%,
    97.8% 0%,
    100% 10%,
    97.8% 20%,
    100% 30%,
    97.8% 40%,
    100% 50%,
    97.8% 60%,
    100% 70%,
    97.8% 80%,
    100% 90%,
    97.8% 100%,
    2.2% 100%,
    0% 90%,
    2.2% 80%,
    0% 70%,
    2.2% 60%,
    0% 50%,
    2.2% 40%,
    0% 30%,
    2.2% 20%,
    0% 10%
  );
}}
/* Trái: xoay + lệch khác phải */
.pl-login-frame--left-s0 {{
  transform: rotate(-7deg) translate(-2%, 3%);
  z-index: 3;
}}
.pl-login-frame--left-s0::before {{ transform: translateX(-50%) rotate(-32deg); }}
.pl-login-frame--left-s1 {{
  transform: rotate(5.5deg) translate(4%, -2%);
  z-index: 4;
}}
.pl-login-frame--left-s1::before {{ transform: translateX(-50%) rotate(28deg); }}
.pl-login-frame--left-s2 {{
  transform: rotate(4deg) translate(-3%, -1%);
  z-index: 5;
}}
.pl-login-frame--left-s2::before {{ transform: translateX(-50%) rotate(-27deg); }}
.pl-login-frame--left-s3 {{
  transform: rotate(-6deg) translate(3%, 2%);
  z-index: 6;
}}
.pl-login-frame--left-s3::before {{ transform: translateX(-50%) rotate(34deg); }}
/* Phải: tách hơn một chút, vẫn đè mép nhẹ */
.pl-login-frame--right-s0 {{
  transform: rotate(6.5deg) translate(1.5%, -1%);
  z-index: 3;
}}
.pl-login-frame--right-s0::before {{ transform: translateX(-50%) rotate(30deg); }}
.pl-login-frame--right-s1 {{
  transform: rotate(-5deg) translate(-1.5%, 1.5%);
  z-index: 5;
}}
.pl-login-frame--right-s1::before {{ transform: translateX(-50%) rotate(-33deg); }}
.pl-login-frame--right-s2 {{
  transform: rotate(-7.5deg) translate(1%, 2%);
  z-index: 4;
}}
.pl-login-frame--right-s2::before {{ transform: translateX(-50%) rotate(26deg); }}
.pl-login-frame--right-s3 {{
  transform: rotate(4.5deg) translate(-1%, -1.5%);
  z-index: 6;
}}
.pl-login-frame--right-s3::before {{ transform: translateX(-50%) rotate(-29deg); }}
.pl-login-frame-inner {{
  border-radius: 0.25em;
  overflow: hidden;
  background: linear-gradient(145deg, #ffe8f0, #fff5f8);
  border: 2px solid rgba(240, 160, 190, 0.55);
  flex: 1 1 auto;
  min-height: 0;
}}
.pl-login-frame-inner img {{
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 22%;
  filter: saturate(0.92) contrast(1.02);
}}
.pl-login-frame figcaption {{
  font-family: "Playfair Display", Georgia, serif;
  font-size: clamp(0.55rem, 0.7vw, 0.75rem);
  color: #a0456a;
  text-align: center;
  padding: 0.45em 0.1em 0.3em;
  letter-spacing: 0.06em;
  flex: 0 0 auto;
}}
@media (max-width: 1100px) {{
  .pl-login-col {{ display: none; }}
}}
</style>
<div class="pl-login-decor" aria-hidden="true">
  {_col_html(left, "left")}
  {_col_html(right, "right")}
</div>
        """,
        unsafe_allow_html=True,
    )


def render_login_gate() -> bool:
    """
    Hiện màn đăng nhập. Trả về True nếu đã đăng nhập (được vào app chính).
    """
    if is_authenticated():
        return True

    _render_login_decor()

    st.markdown(
        f"""
<style>
.pl-welcome-wrap {{
  max-width: 520px;
  margin: 2.5rem auto 2rem auto;
  position: relative;
  z-index: 3;
}}
.pl-welcome-card {{
  background: #ffffff;
  border: 1px solid var(--pl-border, rgba(232,145,176,0.35));
  border-radius: 24px;
  box-shadow: var(--pl-shadow, 0 10px 40px rgba(212,106,146,0.12));
  padding: 1.75rem 1.6rem 1.5rem;
  text-align: center;
}}
.pl-welcome-kicker {{
  display: inline-block;
  font-size: 1rem;
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
  font-size: 3rem !important;
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

            # st.markdown(
            #     '<p class="pl-welcome-hint" style="text-align:center">'
            #     "
            #     "</p>",
            #     unsafe_allow_html=True,
            # )

    return False
