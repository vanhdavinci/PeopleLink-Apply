"""Login gate: DB auth_users + short-lived signed session token.

Token được cất trong cookie trình duyệt (không đưa lên URL), hết hạn theo
PEOPLELINK_AUTH_SESSION_HOURS (mặc định 4h). Secrets chỉ seed user / ký HMAC.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st
from extra_streamlit_components import CookieManager

from app.db import get_conn

# Fallback khi DB trống / chưa seed (local cũ)
DEFAULT_USERNAME = "kimngaan"
DEFAULT_PASSWORD = "230426"
DEFAULT_SESSION_HOURS = 4
DEFAULT_AUTH_SECRET = "peoplelink-local-auth-v1"

# Import mặc định (khớp Secrets / .env)
DEFAULT_AUTH_SEED: dict[str, str] = {
    "ngan.btk": "KimNgaan1202",
    "vietanh": "VietAnh123",
    "admin": "passwordAdmin",
}

SESSION_TOKEN_KEY = "pl_auth_token"
SESSION_USER_KEY = "pl_auth_username"
COOKIE_NAME = "pl_auth_token"
_COOKIE_MGR_STATE = "_pl_cookie_mgr"
_FORCE_LOGOUT_KEY = "_pl_auth_force_logout"
_LEGACY_QUERY_TOKEN_KEY = "pl_auth"

_HASH_PREFIX = "pbkdf2_sha256"
_HASH_ITERATIONS = 120_000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bootstrap_auth_storage() -> CookieManager:
    """Mount cookie bridge — gọi 1 lần đầu mỗi script run, trước check login."""
    cm = CookieManager(key="pl_auth_cookie_mgr")
    st.session_state[_COOKIE_MGR_STATE] = cm
    # Dọn token cũ từng để trên URL (nếu còn)
    try:
        if _LEGACY_QUERY_TOKEN_KEY in st.query_params:
            del st.query_params[_LEGACY_QUERY_TOKEN_KEY]
    except Exception:
        pass
    return cm


def _cookie_manager() -> CookieManager | None:
    cm = st.session_state.get(_COOKIE_MGR_STATE)
    if isinstance(cm, CookieManager):
        return cm
    return None


def _from_secrets(name: str) -> Any | None:
    """Đọc Streamlit Cloud / .streamlit/secrets.toml (không có thì None)."""
    try:
        secrets_obj = st.secrets
    except Exception:
        return None
    try:
        if name in secrets_obj:
            return secrets_obj[name]
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


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        salt_bytes,
        _HASH_ITERATIONS,
    )
    return (
        f"{_HASH_PREFIX}${_HASH_ITERATIONS}$"
        f"{base64.b64encode(salt_bytes).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


def _verify_password(password: str, stored: str) -> bool:
    text = (stored or "").strip()
    if not text.startswith(f"{_HASH_PREFIX}$"):
        # Legacy plaintext (không dùng nữa, nhưng an toàn khi migrate)
        return hmac.compare_digest(password or "", text)
    try:
        _prefix, iter_s, salt_b64, dig_b64 = text.split("$", 3)
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(dig_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False
    got = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(got, expected)


def _accounts_from_secrets_or_env() -> dict[str, str]:
    """Đọc map user→password từ Secrets / env (để seed DB)."""
    users_secret = _from_secrets("PEOPLELINK_AUTH_USERS")
    if isinstance(users_secret, dict) and users_secret:
        return {
            str(user).strip(): str(password)
            for user, password in users_secret.items()
            if str(user).strip()
        }

    raw = ""
    if isinstance(users_secret, str):
        raw = users_secret.strip()
    if not raw:
        raw = (os.getenv("PEOPLELINK_AUTH_USERS") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict) and data:
            return {
                str(user).strip(): str(password)
                for user, password in data.items()
                if str(user).strip()
            }

    user = _setting_str("PEOPLELINK_AUTH_USERNAME", "")
    password = _setting_str("PEOPLELINK_AUTH_PASSWORD", "")
    if user and password:
        return {user: password}
    return {}


def list_auth_usernames() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT username FROM auth_users ORDER BY username"
        ).fetchall()
    return [str(r["username"]) for r in rows]


def auth_user_exists(username: str) -> bool:
    user = (username or "").strip()
    if not user:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM auth_users WHERE username = ?", (user,)
        ).fetchone()
    return row is not None


def upsert_auth_user(username: str, password: str) -> None:
    user = (username or "").strip()
    if not user or not password:
        return
    now = _now()
    pw_hash = _hash_password(password)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO auth_users (username, password_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                updated_at = excluded.updated_at
            """,
            (user, pw_hash, now, now),
        )


def seed_auth_users() -> int:
    """
    Import / cập nhật tài khoản đăng nhập vào bảng auth_users.
    Ưu tiên Secrets/env; luôn đảm bảo DEFAULT_AUTH_SEED có trong DB.
    """
    accounts = dict(DEFAULT_AUTH_SEED)
    accounts.update(_accounts_from_secrets_or_env())
    if not accounts:
        accounts = {DEFAULT_USERNAME: DEFAULT_PASSWORD}
    for user, password in accounts.items():
        upsert_auth_user(user, password)
    return len(accounts)


def load_accounts() -> dict[str, str]:
    """
    Username → placeholder (không trả password thật).
    Dùng để liệt kê / kiểm tra user còn tồn tại.
    """
    names = list_auth_usernames()
    if names:
        return {name: "" for name in names}
    # DB chưa có → seed rồi đọc lại
    seed_auth_users()
    return {name: "" for name in list_auth_usernames()}


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
    if not user or not auth_user_exists(user):
        return None
    return payload


def _cookie_token_raw() -> str:
    cm = _cookie_manager()
    if cm is None:
        return ""
    try:
        val = cm.get(COOKIE_NAME)
    except Exception:
        return ""
    return str(val or "").strip()


def _unique_cookie_key(prefix: str) -> str:
    # CookieManager cần key mới mỗi lần set/delete thì component mới chạy lại.
    return f"{prefix}_{int(time.time() * 1000)}"


def _set_cookie_token(token: str) -> None:
    """Cất token vào cookie browser; Max-Age = TTL session."""
    cm = _cookie_manager()
    if cm is None:
        return
    text = (token or "").strip()
    try:
        ttl = session_ttl_seconds()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        cm.set(
            COOKIE_NAME,
            text,
            key=_unique_cookie_key("pl_auth_cookie_set"),
            path="/",
            expires_at=expires_at,
            max_age=float(ttl),
            same_site="lax",
        )
    except Exception:
        pass


def _delete_cookie_token() -> None:
    """Xóa cookie: max_age=0 + expires quá khứ (delete() của lib hay fail/race)."""
    cm = _cookie_manager()
    if cm is None:
        return
    try:
        cm.set(
            COOKIE_NAME,
            "",
            key=_unique_cookie_key("pl_auth_cookie_clear"),
            path="/",
            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
            max_age=0.0,
            same_site="lax",
        )
        if isinstance(cm.cookies, dict):
            cm.cookies.pop(COOKIE_NAME, None)
    except Exception:
        pass
    try:
        cm.delete(COOKIE_NAME, key=_unique_cookie_key("pl_auth_cookie_del"))
    except Exception:
        pass


def _store_token(token: str, username: str) -> None:
    st.session_state.pop(_FORCE_LOGOUT_KEY, None)
    st.session_state[SESSION_TOKEN_KEY] = token
    st.session_state[SESSION_USER_KEY] = username
    _set_cookie_token(token)


def _clear_token_storage() -> None:
    st.session_state.pop(SESSION_TOKEN_KEY, None)
    st.session_state.pop(SESSION_USER_KEY, None)
    st.session_state[_FORCE_LOGOUT_KEY] = True
    _delete_cookie_token()


def _load_token() -> str:
    # Sau logout: không hydrate lại từ cookie cho đến khi cookie thật sự hết.
    if st.session_state.get(_FORCE_LOGOUT_KEY):
        leftover = _cookie_token_raw()
        if leftover:
            _delete_cookie_token()
            return ""
        st.session_state.pop(_FORCE_LOGOUT_KEY, None)
        return ""

    token = str(st.session_state.get(SESSION_TOKEN_KEY) or "").strip()
    if token:
        return token

    # F5 / session Streamlit mới: lấy từ cookie nếu còn hạn.
    token = _cookie_token_raw()
    if not token:
        return ""
    payload = parse_token(token)
    if payload is None:
        _delete_cookie_token()
        return ""
    st.session_state[SESSION_TOKEN_KEY] = token
    st.session_state[SESSION_USER_KEY] = str(payload["u"])
    return token


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
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM auth_users WHERE username = ?",
            (user,),
        ).fetchone()
    if row is None:
        # DB trống → seed rồi thử lại 1 lần
        if not list_auth_usernames():
            seed_auth_users()
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT password_hash FROM auth_users WHERE username = ?",
                    (user,),
                ).fetchone()
        if row is None:
            hmac.compare_digest(password or "", "\0" * 16)
            return False
    return _verify_password(password or "", str(row["password_hash"] or ""))


def login(*, username: str, password: str) -> dict[str, Any]:
    """Validate against DB auth_users; issue short-lived token."""
    ok = verify_credentials(username=username, password=password)
    user = (username or "").strip()
    if ok:
        st.session_state.pop(_FORCE_LOGOUT_KEY, None)
        token = issue_token(user)
        _store_token(token, user)
    return {
        "ok": ok,
        "username": user,
        "ttl_seconds": session_ttl_seconds() if ok else 0,
    }


def logout() -> None:
    _clear_token_storage()
