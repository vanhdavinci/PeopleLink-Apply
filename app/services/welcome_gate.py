"""Welcome gate: phone + love date unlock (persisted in settings)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.db import get_setting, set_setting

SETTING_PHONE = "welcome_phone"
SETTING_LOVE_DATE = "welcome_love_date"
SETTING_UNLOCKED = "welcome_unlocked_at"

# Giá trị đúng để vào app
EXPECTED_PHONE = "0934086216"
EXPECTED_LOVE_DATE = date(2026, 4, 23)  # 230426 → 23/04/26


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    return digits


def love_date_iso(d: date) -> str:
    return d.isoformat()


def parse_love_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d%m%y", "%d%m%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def is_unlocked() -> bool:
    phone = normalize_phone(get_setting(SETTING_PHONE, "") or "")
    love = parse_love_date(get_setting(SETTING_LOVE_DATE, "") or "")
    if not phone or love is None:
        return False
    return phone == EXPECTED_PHONE and love == EXPECTED_LOVE_DATE


def get_saved_gate() -> dict[str, Any]:
    phone = get_setting(SETTING_PHONE, "") or ""
    love_raw = get_setting(SETTING_LOVE_DATE, "") or ""
    love = parse_love_date(love_raw)
    return {
        "phone": phone,
        "love_date": love,
        "love_date_iso": love_raw,
        "unlocked_at": get_setting(SETTING_UNLOCKED, "") or "",
        "is_unlocked": is_unlocked(),
    }


def save_gate_attempt(*, phone: str, love_date: date) -> dict[str, Any]:
    """Lưu 2 giá trị vào DB; trả về kết quả đúng/sai."""
    phone_n = normalize_phone(phone)
    set_setting(SETTING_PHONE, phone_n)
    set_setting(SETTING_LOVE_DATE, love_date_iso(love_date))

    ok = phone_n == EXPECTED_PHONE and love_date == EXPECTED_LOVE_DATE
    if ok:
        set_setting(
            SETTING_UNLOCKED,
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        )
    return {
        "ok": ok,
        "phone": phone_n,
        "love_date": love_date_iso(love_date),
    }
