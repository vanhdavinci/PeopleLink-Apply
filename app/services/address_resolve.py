"""Parse FullAddress → province/district/ward; classify old vs new; apply mapping."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from app.db import get_conn
from app.services.locations import (
    district_option_value,
    province_option_value,
    resolve_location_fields,
    ward_option_value,
)
from app.services.ward_mapping import lookup_new_to_old

# Payload / UI fields
ADDR_STATUS_OLD = "old_ok"  # đủ Prov/Dist/Ward portal
ADDR_STATUS_PARTIAL = "partial"  # tách được một phần, cấp thiếu để trống
ADDR_STATUS_NEW = "new_needs_confirm"  # địa chỉ mới → cần chọn gợi ý
ADDR_STATUS_UNRESOLVED = "unresolved"  # không nhận ra gì
ADDR_STATUS_CONFIRMED = "confirmed"  # user đã xác nhận map new→old
ADDR_STATUS_KEPT = "kept"  # user chọn giữ nguyên (không map)
ADDR_STATUS_EMPTY = "empty"

STATUS_ICON = {
    ADDR_STATUS_OLD: "✓",
    ADDR_STATUS_PARTIAL: "…",
    ADDR_STATUS_NEW: "★",
    ADDR_STATUS_UNRESOLVED: "?",
    ADDR_STATUS_CONFIRMED: "✓",
    ADDR_STATUS_KEPT: "·",
    ADDR_STATUS_EMPTY: "",
}


def _norm(text: str) -> str:
    raw = unicodedata.normalize("NFC", (text or "").strip())
    raw = re.sub(r"\s+", " ", raw)
    return raw.casefold()


def _fold_vn(text: str) -> str:
    """So khớp không dấu (hoà ≈ hòa)."""
    raw = unicodedata.normalize("NFD", (text or "").strip())
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    raw = re.sub(r"\s+", " ", raw)
    return raw.casefold()


def _name_eq(a: str, b: str) -> bool:
    return _norm(a) == _norm(b) or _fold_vn(a) == _fold_vn(b)


def _name_soft(a: str, b: str) -> bool:
    fa, fb = _fold_vn(a), _fold_vn(b)
    return bool(fa and fb and (fa in fb or fb in fa))


def _strip_admin_prefix(text: str) -> str:
    t = (text or "").strip()
    for prefix in (
        "thành phố ",
        "tp. ",
        "tp ",
        "tỉnh ",
        "quận ",
        "huyện ",
        "thị xã ",
        "thị trấn ",
        "phường ",
        "xã ",
        "p. ",
        "p ",
        "q. ",
        "q ",
        "h. ",
        "h ",
    ):
        if t.casefold().startswith(prefix):
            return t[len(prefix) :].strip()
    return t


_PROVINCE_ALIASES: list[tuple[str, str]] = [
    # longer first
    ("thành phố hồ chí minh", "Thành phố Hồ Chí Minh"),
    ("tp. hồ chí minh", "Thành phố Hồ Chí Minh"),
    ("tp hồ chí minh", "Thành phố Hồ Chí Minh"),
    ("tp.hcm", "Thành phố Hồ Chí Minh"),
    ("tp hcm", "Thành phố Hồ Chí Minh"),
    ("tphcm", "Thành phố Hồ Chí Minh"),
    ("hcm", "Thành phố Hồ Chí Minh"),
    ("hà nội", "Thành phố Hà Nội"),
    ("ha noi", "Thành phố Hà Nội"),
]

_ADMIN_SPLIT_RE = re.compile(
    r"(?=\b(?:phường|xã|thị\s+trấn|quận|huyện|thị\s+xã|tỉnh|thành\s+phố)\b)",
    re.IGNORECASE,
)
_Q_DISTRICT_RE = re.compile(r"\b[Qq]\.?\s*(\d{1,2})\b")
_P_WARD_RE = re.compile(r"\b[Pp]\.\s*(?=[^\s])")


def _expand_aliases(text: str) -> str:
    """TPHCM / Q12 / P.Name → dạng đầy đủ để tách."""
    t = unicodedata.normalize("NFC", (text or "").strip())
    t = re.sub(r"\s+", " ", t)
    t = _Q_DISTRICT_RE.sub(r"Quận \1", t)
    t = _P_WARD_RE.sub("Phường ", t)

    lower = t.casefold()
    # Already full city names — don't re-expand shorter aliases into them
    if "thành phố hồ chí minh" in lower or "thành phố hà nội" in lower:
        return t

    for alias, full in _PROVINCE_ALIASES:
        pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
        if pattern.search(t):
            # avoid "Thành phố " + "Thành phố Hà Nội"
            t = pattern.sub(full, t)
            t = re.sub(
                r"(?i)\bthành phố\s+thành phố\b",
                "Thành phố",
                t,
            )
            break
    return t


def _split_parts(full: str) -> list[str]:
    """
    Tách địa chỉ:
    1) theo dấu phẩy / gạch
    2) nếu 1 đoạn: tách theo từ khóa phường|xã|quận|huyện|tỉnh|thành phố
    """
    text = _expand_aliases(full)
    if not text:
        return []

    parts = re.split(r"\s*,\s*|\s+-\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        return parts

    # free-form: "... Phường X Quận Y Thành phố Z"
    keyword_parts = [p.strip() for p in _ADMIN_SPLIT_RE.split(text) if p.strip()]
    if len(keyword_parts) >= 2:
        return keyword_parts
    return parts


def _classify_part(part: str) -> str:
    n = _norm(part)
    if n.startswith("phường") or n.startswith("xã") or n.startswith("thị trấn"):
        return "ward"
    if n.startswith("quận") or n.startswith("huyện") or n.startswith("thị xã"):
        return "district"
    if n.startswith("tỉnh") or n.startswith("thành phố"):
        return "province"
    return "other"


def _organize_parts(parts: list[str]) -> tuple[str, str, str, str]:
    """Return (street, ward, district, province) guesses from ordered parts."""
    street_bits: list[str] = []
    ward = ""
    district = ""
    province = ""
    for part in parts:
        kind = _classify_part(part)
        if kind == "ward" and not ward:
            ward = part
        elif kind == "district" and not district:
            district = part
        elif kind == "province" and not province:
            province = part
        else:
            street_bits.append(part)
    # If trailing parts were unmarked (comma style), fall back to position
    if not province and parts:
        # classic: last = province, -2 district or ward
        if not ward and not district:
            if len(parts) == 1:
                # một cụm free-text — không gán cả chuỗi thành tỉnh
                street_bits = list(parts)
            elif len(parts) >= 3:
                province = parts[-1]
                district = parts[-2]
                ward = parts[-3]
                street_bits = parts[:-3]
            elif len(parts) == 2:
                province = parts[-1]
                ward = parts[-2]
                street_bits = parts[:-2]
        elif not province:
            province = parts[-1]
            street_bits = [p for p in street_bits if p != parts[-1]]
    return ", ".join(street_bits), ward, district, province


@dataclass
class AddressSuggestion:
    label: str
    portal_ward_value: str
    old_ward: str
    old_district: str
    old_province: str
    old_full_address: str
    mapping_type: str
    is_default: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AddressResolveResult:
    full_address: str
    street: str = ""
    province: str = ""
    district: str = ""
    ward: str = ""
    status: str = ADDR_STATUS_EMPTY
    note: str = ""
    icon: str = ""
    suggestions: list[AddressSuggestion] = field(default_factory=list)

    def to_row_fields(self) -> dict[str, str]:
        return {
            "FullAddress": self.full_address,
            "AddrTmpStreet": self.street,
            "AddrTmpProvince": self.province,
            "AddrTmpDistrict": self.district,
            "AddrTmpWard": self.ward,
            "AddressStatus": self.status,
            "AddressNote": self.note,
            "AddressIcon": self.icon or STATUS_ICON.get(self.status, ""),
        }


def _match_province(name: str) -> dict[str, Any] | None:
    target = _strip_admin_prefix(name) or name
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT code, name, inserted_value FROM provinces"
        ).fetchall()
    best = None
    for r in rows:
        if _name_eq(r["name"], name) or _name_eq(r["name"], target):
            return dict(r)
        if _name_eq(_strip_admin_prefix(r["name"]), target):
            return dict(r)
        if _name_soft(target, _strip_admin_prefix(r["name"])) or _name_soft(
            target, r["name"]
        ):
            best = dict(r)
    return best


def _match_district(name: str, province_code: str) -> dict[str, Any] | None:
    target = _strip_admin_prefix(name) or name
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, province_code, name, inserted_value
            FROM districts WHERE province_code = ?
            """,
            (province_code,),
        ).fetchall()
    best = None
    for r in rows:
        if _name_eq(r["name"], name) or _name_eq(r["name"], target):
            return dict(r)
        if _name_eq(_strip_admin_prefix(r["name"]), target):
            return dict(r)
        if _name_soft(target, _strip_admin_prefix(r["name"])) or _name_soft(
            target, r["name"]
        ):
            best = dict(r)
    return best


def _match_ward(name: str, district_id: int) -> dict[str, Any] | None:
    target = _strip_admin_prefix(name) or name
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, district_id, name, inserted_value
            FROM wards WHERE district_id = ?
            """,
            (district_id,),
        ).fetchall()
    best = None
    for r in rows:
        if _name_eq(r["name"], name) or _name_eq(r["name"], target):
            return dict(r)
        if _name_eq(_strip_admin_prefix(r["name"]), target):
            return dict(r)
        if _name_soft(target, _strip_admin_prefix(r["name"])) or _name_soft(
            target, r["name"]
        ):
            best = dict(r)
    return best


def _portal_fields_from_ward_id(ward_id: int | str) -> dict[str, str] | None:
    wid = str(ward_id).strip()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                w.id AS ward_id, w.name AS ward_name, w.inserted_value AS ward_value,
                d.id AS district_id, d.name AS district_name, d.inserted_value AS district_value,
                p.code AS province_code, p.name AS province_name, p.inserted_value AS province_value
            FROM wards w
            JOIN districts d ON d.id = w.district_id
            JOIN provinces p ON p.code = d.province_code
            WHERE CAST(w.id AS TEXT) = ? OR w.inserted_value = ?
               OR w.inserted_value || '|' || w.name = ?
            LIMIT 1
            """,
            (wid, wid, wid),
        ).fetchone()
    if not row:
        return None
    return {
        "AddrTmpProvince": province_option_value(
            {"inserted_value": row["province_value"], "name": row["province_name"]}
        ),
        "AddrTmpDistrict": district_option_value(
            {
                "id": row["district_id"],
                "inserted_value": row["district_value"],
                "name": row["district_name"],
            }
        ),
        "AddrTmpWard": ward_option_value(
            {
                "id": row["ward_id"],
                "inserted_value": row["ward_value"],
                "name": row["ward_name"],
            }
        ),
    }


def _suggestions_from_mapping(
    new_ward: str, new_province: str
) -> list[AddressSuggestion]:
    # all options (không chỉ default) để user chọn
    rows = lookup_new_to_old(
        new_ward=new_ward,
        new_province=new_province,
        prefer_default=False,
    )
    if not rows and new_ward:
        rows = lookup_new_to_old(new_ward=new_ward, prefer_default=False)

    out: list[AddressSuggestion] = []
    seen: set[str] = set()
    for r in rows:
        key = str(r.get("portal_ward_value") or "") + "|" + str(r.get("old_full_address") or "")
        if key in seen:
            continue
        seen.add(key)
        label = (
            str(r.get("old_full_address") or "").strip()
            or ", ".join(
                x
                for x in (
                    r.get("old_ward"),
                    r.get("old_district"),
                    r.get("old_province"),
                )
                if x
            )
        )
        if not label:
            continue
        out.append(
            AddressSuggestion(
                label=label,
                portal_ward_value=str(r.get("portal_ward_value") or ""),
                old_ward=str(r.get("old_ward") or ""),
                old_district=str(r.get("old_district") or ""),
                old_province=str(r.get("old_province") or ""),
                old_full_address=str(r.get("old_full_address") or label),
                mapping_type=str(r.get("mapping_type") or ""),
                is_default=bool(int(r.get("is_default_new_ward") or 0)),
            )
        )
    # default first
    out.sort(key=lambda s: (0 if s.is_default else 1, s.label))
    return out


def _match_ward_in_province(name: str, province_code: str) -> list[dict[str, Any]]:
    """Ward may omit district — search all districts in province."""
    target = _strip_admin_prefix(name) or name
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT w.id, w.district_id, w.name, w.inserted_value,
                   d.name AS district_name, d.inserted_value AS district_value
            FROM wards w
            JOIN districts d ON d.id = w.district_id
            WHERE d.province_code = ?
            """,
            (province_code,),
        ).fetchall()
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        if _name_eq(r["name"], name) or _name_eq(r["name"], target):
            exact.append(item)
        elif _name_eq(_strip_admin_prefix(r["name"]), target):
            exact.append(item)
        elif _name_soft(target, _strip_admin_prefix(r["name"])):
            fuzzy.append(item)
    return exact or fuzzy


def _match_ward_global(name: str) -> list[dict[str, Any]]:
    """Search ward by name across all provinces (when text province is wrong)."""
    target = _strip_admin_prefix(name) or name
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT w.id, w.district_id, w.name, w.inserted_value,
                   d.name AS district_name, d.inserted_value AS district_value,
                   p.code AS province_code, p.name AS province_name,
                   p.inserted_value AS province_value
            FROM wards w
            JOIN districts d ON d.id = w.district_id
            JOIN provinces p ON p.code = d.province_code
            """
        ).fetchall()
    exact: list[dict[str, Any]] = []
    for r in rows:
        if (
            _name_eq(r["name"], name)
            or _name_eq(r["name"], target)
            or _name_eq(_strip_admin_prefix(r["name"]), target)
        ):
            exact.append(dict(r))
    return exact


def _detect_province_in_text(text: str) -> tuple[dict[str, Any] | None, str]:
    """
    Find province name inside free text (longest match).
    Returns (province_row, remainder_text).
    """
    expanded = _expand_aliases(text)
    lower = _norm(expanded)
    with get_conn() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT code, name, inserted_value FROM provinces"
            ).fetchall()
        ]
    rows.sort(
        key=lambda r: max(len(_norm(r["name"])), len(_norm(_strip_admin_prefix(r["name"])))),
        reverse=True,
    )
    for r in rows:
        candidates = {_norm(r["name"]), _norm(_strip_admin_prefix(r["name"]))}
        for c in sorted(candidates, key=len, reverse=True):
            if len(c) < 3:
                continue
            idx = lower.rfind(c)
            if idx >= 0:
                before = expanded[:idx].strip(" ,;-")
                after = expanded[idx + len(c) :].strip(" ,;-")
                # prefer province at end
                if after and len(after) > len(before):
                    continue
                remainder = before if not after else f"{before} {after}".strip()
                return r, remainder
    return None, expanded


def _raw_label(text: str) -> str:
    return (text or "").strip()


def _set_partial(
    result: AddressResolveResult,
    *,
    street: str = "",
    province: str = "",
    district: str = "",
    ward: str = "",
    note: str = "",
) -> AddressResolveResult:
    """
    Partial hợp lệ: được thiếu phường (lá).
    Không chấp nhận có xã mà thiếu huyện.
    """
    if ward and not district:
        # safety: không bao giờ để xã mà trống huyện
        ward = ""
    result.street = street
    result.province = province
    result.district = district
    result.ward = ward
    missing = []
    if not province:
        missing.append("tỉnh")
    if not district:
        missing.append("huyện/TP")
    # phường thiếu là OK — không liệt vào lỗi bắt buộc
    result.status = ADDR_STATUS_PARTIAL
    result.icon = STATUS_ICON[ADDR_STATUS_PARTIAL]
    base = note or "Đã tách một phần — phường/xã có thể điền sau"
    if missing:
        result.note = f"{base} (thiếu: {', '.join(missing)})"
    elif not ward:
        result.note = f"{base} (phường/xã để trống)"
    else:
        result.note = base
    return result


def resolve_full_address(full_address: str) -> AddressResolveResult:
    """
    Parse one-line address.
    Điền được cấp nào thì điền cấp đó; cấp không đủ → để trống cho user.
    """
    full = (full_address or "").strip()
    result = AddressResolveResult(full_address=full)
    if not full:
        result.status = ADDR_STATUS_EMPTY
        result.icon = STATUS_ICON[ADDR_STATUS_EMPTY]
        return result

    parts = _split_parts(full)
    street, ward_name, dist_name, prov_name = _organize_parts(parts)

    # Free text / tỉnh chưa rõ: dò tỉnh trong chuỗi (vd "đức hoà long an")
    if not prov_name or not _match_province(prov_name):
        detected, remainder = _detect_province_in_text(full)
        if detected:
            prov_name = detected["name"]
            rem_parts = _split_parts(remainder) if remainder else []
            if not rem_parts and remainder:
                rem_parts = [remainder]
            if rem_parts:
                if len(rem_parts) == 1 and not dist_name and not ward_name:
                    dist_name = rem_parts[0]
                else:
                    s2, w2, d2, _p2 = _organize_parts(rem_parts)
                    street = street or s2
                    ward_name = ward_name or w2
                    dist_name = dist_name or d2 or (
                        rem_parts[0] if len(rem_parts) == 1 else dist_name
                    )
            if not street and remainder and not ward_name and not dist_name:
                street = remainder

    if len(parts) >= 2 and not prov_name:
        prov_name = parts[-1]
    if len(parts) >= 2 and not ward_name and not dist_name:
        # "A, Province" — chưa biết A là huyện hay xã
        mid = parts[-2]
        if _classify_part(mid) == "ward":
            ward_name = mid
        elif _classify_part(mid) == "district":
            dist_name = mid
        else:
            # thử huyện trước khi gán xã
            dist_name = mid

    # Chỉ có tỉnh
    if prov_name and not ward_name and not dist_name:
        prov = _match_province(prov_name)
        if prov:
            return _set_partial(
                result,
                street=street,
                province=province_option_value(prov),
                note="Chỉ nhận được tỉnh — cần huyện (phường có thể để trống)",
            )
        return _set_partial(
            result,
            street=street,
            province=_raw_label(prov_name),
            note="Tỉnh theo text (chưa khớp DB) — cần huyện",
        )

    if not prov_name:
        result.status = ADDR_STATUS_UNRESOLVED
        result.note = "Không nhận được tỉnh/thành trong địa chỉ"
        result.icon = STATUS_ICON[ADDR_STATUS_UNRESOLVED]
        result.street = full
        return result

    prov = _match_province(prov_name)
    prov_value = province_option_value(prov) if prov else _raw_label(prov_name)
    prov_code = prov["code"] if prov else None

    dist_row = None
    ward_row = None

    # 1) Ưu tiên khớp huyện (bắt buộc có trên cây; phường mới được thiếu)
    if dist_name and prov_code:
        dist_row = _match_district(dist_name, prov_code)

    # 2) Token giữa chưa rõ: thử huyện trước, mới tới xã
    #    (không được điền xã mà bỏ trống huyện)
    ambiguous_mid = ""
    if not dist_row and not ward_name and dist_name:
        ambiguous_mid = dist_name
    elif not dist_row and ward_name and not dist_name:
        # đã gắn nhầm thành xã từ organize — vẫn thử huyện trước
        if _classify_part(ward_name) != "ward":
            ambiguous_mid = ward_name

    if ambiguous_mid and prov_code and not dist_row:
        dist_row = _match_district(ambiguous_mid, prov_code)
        if dist_row:
            # đây là huyện, không phải xã
            if ward_name == ambiguous_mid:
                ward_name = ""
            dist_name = ambiguous_mid
        elif not ward_name:
            # chưa phải huyện trong tỉnh này → mới coi là xã
            ward_name = ambiguous_mid
            dist_name = ""

    # 3) Xã (lá): chỉ khi đã có hướng huyện, hoặc suy huyện từ xã
    if ward_name and prov_code:
        if dist_row:
            ward_row = _match_ward(ward_name, int(dist_row["id"]))
        if not ward_row:
            found = _match_ward_in_province(ward_name, prov_code)
            if len(found) == 1:
                # suy huyện từ xã (bắt buộc có huyện)
                ward_row = found[0]
                with get_conn() as conn:
                    drow = conn.execute(
                        "SELECT id, name, inserted_value FROM districts WHERE id = ?",
                        (ward_row["district_id"],),
                    ).fetchone()
                if drow:
                    dist_row = dict(drow)
            elif len(found) > 1:
                result.street = street
                result.province = prov_value
                result.status = ADDR_STATUS_NEW
                result.note = (
                    f"Nhiều phường/xã «{_strip_admin_prefix(ward_name)}» trong tỉnh — "
                    "chọn gợi ý để lấy đủ huyện + xã"
                )
                result.icon = STATUS_ICON[ADDR_STATUS_NEW]
                for w in found:
                    with get_conn() as conn:
                        drow = conn.execute(
                            "SELECT name FROM districts WHERE id = ?",
                            (w["district_id"],),
                        ).fetchone()
                    dname = drow["name"] if drow else ""
                    label = f"{w['name']}, {dname}, {prov['name'] if prov else prov_name}"
                    result.suggestions.append(
                        AddressSuggestion(
                            label=label,
                            portal_ward_value=str(w["id"]),
                            old_ward=str(w["name"]),
                            old_district=dname,
                            old_province=str(prov["name"] if prov else prov_name),
                            old_full_address=label,
                            mapping_type="ambiguous",
                            is_default=False,
                        )
                    )
                return result

    # Đủ tỉnh + huyện + xã
    if prov and dist_row and ward_row:
        result.street = street
        result.province = prov_value
        result.district = district_option_value(dist_row)
        result.ward = ward_option_value(ward_row)
        result.status = ADDR_STATUS_OLD
        result.note = "Địa chỉ cũ — đã tách Province/District/Ward"
        result.icon = STATUS_ICON[ADDR_STATUS_OLD]
        return result

    # Tỉnh + huyện đủ; phường (lá) được để trống cho user điền sau
    if prov and dist_row and not ward_row:
        return _set_partial(
            result,
            street=street,
            province=prov_value,
            district=district_option_value(dist_row),
            ward="",
            note="Đã tách tỉnh + huyện — phường/xã để trống (điền sau)",
        )

    # Có tên xã nhưng chưa suy được huyện → không được điền xã bỏ trống huyện
    if ward_name and prov and not dist_row:
        suggestions = _suggestions_from_mapping(ward_name, prov["name"])
        if not suggestions:
            suggestions = _suggestions_from_mapping(ward_name, prov_name)
        if suggestions:
            result.street = street
            result.province = prov_value
            result.status = ADDR_STATUS_NEW
            result.note = (
                f"Địa chỉ mới «{_strip_admin_prefix(ward_name)}» — "
                "chọn gợi ý để lấy huyện + xã (không bỏ trống huyện)"
            )
            result.icon = STATUS_ICON[ADDR_STATUS_NEW]
            result.suggestions = suggestions
            return result

        global_wards = _match_ward_global(ward_name)
        if global_wards:
            result.street = street
            result.province = prov_value
            result.status = ADDR_STATUS_NEW
            result.note = (
                f"Chưa suy được huyện cho «{_strip_admin_prefix(ward_name)}» "
                f"trong «{prov['name']}» — có {len(global_wards)} gợi ý tỉnh khác"
            )
            result.icon = STATUS_ICON[ADDR_STATUS_NEW]
            for w in global_wards:
                label = f"{w['name']}, {w['district_name']}, {w['province_name']}"
                result.suggestions.append(
                    AddressSuggestion(
                        label=label,
                        portal_ward_value=str(w["id"]),
                        old_ward=str(w["name"]),
                        old_district=str(w["district_name"]),
                        old_province=str(w["province_name"]),
                        old_full_address=label,
                        mapping_type="cross_province",
                        is_default=False,
                    )
                )
            return result

        # Không điền ward khi thiếu district
        return _set_partial(
            result,
            street=street,
            province=prov_value,
            district="",
            ward="",
            note=(
                f"Có nhắc «{_strip_admin_prefix(ward_name)}» nhưng chưa suy được huyện — "
                "huyện bắt buộc; phường để trống đến khi chọn/điền huyện"
            ),
        )

    # Huyện theo text chưa khớp DB
    if dist_name and not dist_row:
        return _set_partial(
            result,
            street=street,
            province=prov_value,
            district=_raw_label(dist_name),
            ward="",
            note="Huyện theo text (chưa khớp DB) — phường để trống",
        )

    if prov_value:
        return _set_partial(
            result,
            street=street,
            province=prov_value,
            note="Chỉ có tỉnh — cần huyện (phường có thể để trống)",
        )

    result.street = full
    result.status = ADDR_STATUS_UNRESOLVED
    result.note = "Không tách được tỉnh / huyện"
    result.icon = STATUS_ICON[ADDR_STATUS_UNRESOLVED]
    return result


def apply_suggestion_to_row(
    row: dict[str, Any], suggestion: AddressSuggestion | dict[str, Any]
) -> dict[str, str]:
    """Confirm new→old: fill portal AddrTmp* from selected mapping suggestion."""
    if isinstance(suggestion, dict):
        sug = AddressSuggestion(
            label=str(suggestion.get("label") or ""),
            portal_ward_value=str(suggestion.get("portal_ward_value") or ""),
            old_ward=str(suggestion.get("old_ward") or ""),
            old_district=str(suggestion.get("old_district") or ""),
            old_province=str(suggestion.get("old_province") or ""),
            old_full_address=str(suggestion.get("old_full_address") or ""),
            mapping_type=str(suggestion.get("mapping_type") or ""),
            is_default=bool(suggestion.get("is_default")),
        )
    else:
        sug = suggestion

    portal = _portal_fields_from_ward_id(sug.portal_ward_value)
    if not portal:
        # fallback: try match old names in location DB
        prov = _match_province(sug.old_province)
        if not prov:
            raise ValueError(
                f"Không tìm thấy ward portal id={sug.portal_ward_value} trong DB locations."
            )
        dist = _match_district(sug.old_district, prov["code"])
        if not dist:
            raise ValueError(f"Không tìm huyện: {sug.old_district}")
        ward = _match_ward(sug.old_ward, int(dist["id"]))
        if not ward:
            raise ValueError(f"Không tìm phường: {sug.old_ward}")
        portal = {
            "AddrTmpProvince": province_option_value(prov),
            "AddrTmpDistrict": district_option_value(dist),
            "AddrTmpWard": ward_option_value(ward),
        }

    out = dict(row)
    out.update(portal)
    out.update(resolve_location_fields(out))
    out["AddressStatus"] = ADDR_STATUS_CONFIRMED
    out["AddressIcon"] = STATUS_ICON[ADDR_STATUS_CONFIRMED]
    out["AddressNote"] = f"Đã xác nhận map → {sug.old_full_address or sug.label}"
    # Keep FullAddress as original for audit; street giữ nguyên nếu có
    if not out.get("AddrTmpStreet"):
        out["AddrTmpStreet"] = str(row.get("AddrTmpStreet") or "")
    return {k: "" if v is None else str(v) for k, v in out.items()}


def mark_address_kept(row: dict[str, Any]) -> dict[str, str]:
    out = dict(row)
    out["AddressStatus"] = ADDR_STATUS_KEPT
    out["AddressIcon"] = STATUS_ICON[ADDR_STATUS_KEPT]
    out["AddressNote"] = "Giữ nguyên — chưa map sang địa chỉ cũ"
    return {k: "" if v is None else str(v) for k, v in out.items()}


def enrich_row_address(row: dict[str, Any], *, force: bool = False) -> dict[str, str]:
    """
    Resolve FullAddress into AddrTmp* + status.
    Skip if already confirmed/kept/old_ok unless force=True.
    Also re-resolve when FullAddress present and status empty/new/unresolved.
    """
    out = {k: "" if v is None else str(v) for k, v in dict(row).items()}
    status = (out.get("AddressStatus") or "").strip()
    full = (out.get("FullAddress") or "").strip()

    # Legacy rows: already have Prov/Dist/Ward, no FullAddress
    if not full:
        if out.get("AddrTmpProvince") and out.get("AddrTmpWard"):
            out.update(resolve_location_fields(out))
            if not status:
                out["AddressStatus"] = ADDR_STATUS_OLD
                out["AddressIcon"] = STATUS_ICON[ADDR_STATUS_OLD]
                out["AddressNote"] = "Địa chỉ tách sẵn (legacy)"
            return out
        out["AddressStatus"] = ADDR_STATUS_EMPTY
        out["AddressIcon"] = ""
        out["AddressNote"] = ""
        return out

    if not force and status in {
        ADDR_STATUS_CONFIRMED,
        ADDR_STATUS_KEPT,
        ADDR_STATUS_OLD,
    }:
        # still refresh icon
        out["AddressIcon"] = STATUS_ICON.get(status, out.get("AddressIcon") or "")
        return out

    resolved = resolve_full_address(full)
    fields = resolved.to_row_fields()
    out.update(fields)
    if resolved.status in {ADDR_STATUS_OLD, ADDR_STATUS_PARTIAL, ADDR_STATUS_CONFIRMED}:
        out.update(resolve_location_fields(out))
    # stash suggestion count in note only; suggestions looked up again in modal
    return out


def suggestions_for_row(row: dict[str, Any]) -> list[AddressSuggestion]:
    full = str(row.get("FullAddress") or "").strip()
    if not full:
        return []
    return resolve_full_address(full).suggestions


def enrich_rows(rows: list[dict[str, Any]], *, force: bool = False) -> list[dict[str, str]]:
    return [enrich_row_address(r, force=force) for r in rows]
