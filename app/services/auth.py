"""Login gate: multi-account username/password + short-lived signed session token."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import streamlit as st

# Defaults for local app — override via .env hoặc Streamlit Secrets
DEFAULT_USERNAME = "kimngaan"
DEFAULT_PASSWORD = "230426"
DEFAULT_SESSION_HOURS = 4
DEFAULT_AUTH_SECRET = "peoplelink-local-auth-v1"

SESSION_TOKEN_KEY = "pl_auth_token"
SESSION_USER_KEY = "pl_auth_username"


def _from_secrets(name: str) -> Any | None:
    """Đọc Streamlit Cloud / .streamlit/secrets.toml (không có thì None)."""
    try:
        secrets = st.secrets
    except Exception:
        return None
    try:
        if name in secrets:
            return secrets[name]
    except Exception:
        return None
    return None


def _setting_str(name: str, default: str = "") -> str:
    val = _from_secrets(name)
    if val is None:
        return (os.getenv(name) or default).strip()
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val).strip()


def session_ttl_seconds() -> int:
    raw = _setting_str(
        "PEOPLELINK_AUTH_SESSION_HOURS", str(DEFAULT_SESSION_HOURS)
    )
    try:
        hours = float(raw)
    except ValueError:
        hours = float(DEFAULT_SESSION_HOURS)
    return max(60, int(hours * 3600))


def _secret() -> bytes:
    return (
        _setting_str("PEOPLELINK_AUTH_SECRET") or DEFAULT_AUTH_SECRET
    ).encode("utf-8")


def load_accounts() -> dict[str, str]:
    """
    Map username → password.

    Nguồn (theo thứ tự):
      1. st.secrets PEOPLELINK_AUTH_USERS — dict TOML hoặc chuỗi JSON
      2. env PEOPLELINK_AUTH_USERS (JSON)
      3. PEOPLELINK_AUTH_USERNAME + PEOPLELINK_AUTH_PASSWORD / default
    """
    users_secret = _from_secrets("PEOPLELINK_AUTH_USERS")
    if isinstance(users_secret, dict) and users_secret:
        accounts = {
            str(user).strip(): str(password)
            for user, password in users_secret.items()
            if str(user).strip()
        }
        if accounts:
            return accounts

    raw = ""
    if isinstance(users_secret, str):
        raw = users_secret.strip()
    if not raw:
        raw = (os.getenv("PEOPLELINK_AUTH_USERS") or "").strip()

    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "PEOPLELINK_AUTH_USERS phải là JSON object "
                '{"user1":"pass1","user2":"pass2",...}'
            ) from exc
        if not isinstance(data, dict) or not data:
            raise ValueError("PEOPLELINK_AUTH_USERS phải là object không rỗng")
        accounts = {
            str(user).strip(): str(password)
            for user, password in data.items()
            if str(user).strip()
        }
        if not accounts:
            raise ValueError("PEOPLELINK_AUTH_USERS không có username hợp lệ")
        return accounts

    user = _setting_str("PEOPLELINK_AUTH_USERNAME", DEFAULT_USERNAME)
    password = _setting_str("PEOPLELINK_AUTH_PASSWORD", DEFAULT_PASSWORD) or DEFAULT_PASSWORD
    return {user: password}


def account_usernames() -> list[str]:
    return sorted(load_accounts().keys())


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def issue_token(username: str, *, ttl_seconds: int | None = None) -> str:
    """JWT-like compact token: base64(payload).hmac_sha256."""
    now = int(time.time())
    ttl = ttl_seconds if ttl_seconds is not None else session_ttl_seconds()
    payload = {
        "u": (username or "").strip(),
        "iat": now,
        "exp": now + ttl,
    }
    body = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token: str | None) -> dict[str, Any] | None:
    """Verify signature + expiry + user still exists. Returns payload or None."""
    text = (token or "").strip()
    if not text or "." not in text:
        return None
    body, sig = text.rsplit(".", 1)
    if not body or not sig:
        return None
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        exp = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return None
    if exp <= int(time.time()):
        return None
    user = str(payload.get("u") or "").strip()
    if not user or user not in load_accounts():
        return None
    return payload


def _store_token(token: str, username: str) -> None:
    # Chỉ lưu theo phiên browser (session_state) — nhiều account không đụng token chung.
    st.session_state[SESSION_TOKEN_KEY] = token
    st.session_state[SESSION_USER_KEY] = username


def _clear_token_storage() -> None:
    st.session_state.pop(SESSION_TOKEN_KEY, None)
    st.session_state.pop(SESSION_USER_KEY, None)


def _load_token() -> str:
    return str(st.session_state.get(SESSION_TOKEN_KEY) or "").strip()


def _maybe_slide_refresh(payload: dict[str, Any], token: str) -> str:
    """Gia hạn token khi còn dưới 50% TTL (sliding session)."""
    try:
        exp = int(payload["exp"])
        iat = int(payload.get("iat") or exp)
    except (KeyError, TypeError, ValueError):
        return token
    ttl = max(1, exp - iat)
    remaining = exp - int(time.time())
    if remaining > ttl // 2:
        return token
    username = str(payload["u"])
    fresh = issue_token(username)
    _store_token(fresh, username)
    return fresh


def is_authenticated() -> bool:
    token = _load_token()
    payload = parse_token(token)
    if payload is None:
        if token:
            _clear_token_storage()
        return False
    username = str(payload["u"])
    st.session_state[SESSION_USER_KEY] = username
    _maybe_slide_refresh(payload, token)
    return True


def current_username() -> str:
    if not is_authenticated():
        return ""
    return str(st.session_state.get(SESSION_USER_KEY) or "")


def session_expires_in_seconds() -> int | None:
    payload = parse_token(_load_token())
    if payload is None:
        return None
    return max(0, int(payload["exp"]) - int(time.time()))


def verify_credentials(*, username: str, password: str) -> bool:
    user = (username or "").strip()
    accounts = load_accounts()
    expected = accounts.get(user)
    if expected is None:
        # So sánh giả để khó đo thời gian đoán user có tồn tại hay không
        hmac.compare_digest(password or "", "\0" * 16)
        return False
    return hmac.compare_digest(password or "", expected)


def login(*, username: str, password: str) -> dict[str, Any]:
    """Validate against any configured account; issue short-lived token."""
    ok = verify_credentials(username=username, password=password)
    user = (username or "").strip()
    if ok:
        token = issue_token(user)
        _store_token(token, user)
    return {
        "ok": ok,
        "username": user,
        "ttl_seconds": session_ttl_seconds() if ok else 0,
    }


def logout() -> None:
    _clear_token_storage()
