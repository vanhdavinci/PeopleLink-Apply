"""Tab Projects — danh sách thẻ + trang chi tiết (3 phần)."""
from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_quill import st_quill

from app.db import db_stats
from app.services.project_article import (
    add_article_image,
    delete_article_image,
    get_article,
    html_to_plain,
    image_data_uri,
    list_article_images,
    save_article,
)
from app.services.project_service import (
    format_display_date,
    get_project,
    list_projects_for_user,
    project_type_label,
    update_project_link_apply,
)
from app.services.project_sync import mark_expired_projects, sync_projects
from app.services.submitted_candidates import list_submitted_for_project
from app.services.user_service import APP_USER_FULL_NAME


def _esc(text: object) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _clipboard_copy_button(
    *,
    label: str,
    plain: str = "",
    html_content: str = "",
    image_data_uri_value: str = "",
    key: str,
    height: int = 46,
) -> None:
    """Nút copy text/HTML hoặc ảnh (Clipboard API trong trình duyệt)."""
    btn_id = f"copy_btn_{key}"
    status_id = f"copy_status_{key}"
    payload = {
        "plain": plain or "",
        "html": html_content or "",
        "image": image_data_uri_value or "",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    # Escape for embedding in JS string via JSON already
    components.html(
        f"""
<div style="font-family:Nunito,sans-serif">
  <button id="{btn_id}" style="
    width:100%;border:1px solid #f0a0be;background:linear-gradient(135deg,#f0a0be,#e27aa5);
    color:#fff;font-weight:700;border-radius:999px;padding:0.45rem 0.9rem;cursor:pointer;
  ">{html.escape(label)}</button>
  <div id="{status_id}" style="font-size:0.78rem;color:#8a6574;margin-top:0.25rem;min-height:1.1em"></div>
</div>
<script>
const payload = {payload_json};
const btn = document.getElementById("{btn_id}");
const status = document.getElementById("{status_id}");
btn.addEventListener("click", async () => {{
  status.textContent = "Đang copy…";
  try {{
    if (payload.image) {{
      const res = await fetch(payload.image);
      const blob = await res.blob();
      const type = blob.type || "image/png";
      await navigator.clipboard.write([new ClipboardItem({{ [type]: blob }})]);
      status.textContent = "Đã copy ảnh vào clipboard.";
      return;
    }}
    if (payload.html && window.ClipboardItem) {{
      const items = {{
        "text/plain": new Blob([payload.plain || ""], {{ type: "text/plain" }}),
        "text/html": new Blob([payload.html], {{ type: "text/html" }}),
      }};
      await navigator.clipboard.write([new ClipboardItem(items)]);
      status.textContent = "Đã copy bài viết (kèm format).";
      return;
    }}
    await navigator.clipboard.writeText(payload.plain || payload.html || "");
    status.textContent = "Đã copy văn bản.";
  }} catch (err) {{
    status.textContent = "Copy thất bại — trình duyệt chặn clipboard.";
    console.error(err);
  }}
}});
</script>
        """,
        height=height,
    )


def _render_article_section(project_id: int) -> None:
    st.markdown(
        """
<div class="pl-proj-section">
  <h3>2. Bài viết</h3>
  <p class="pl-proj-section-desc">
    Soạn bài (đậm / nghiêng / cỡ chữ), upload ảnh, copy bài hoặc copy từng ảnh.
  </p>
</div>
        """,
        unsafe_allow_html=True,
    )

    article = get_article(project_id)
    st.caption(
        f"Cập nhật: `{article.get('article_updated_at') or 'chưa lưu'}` · "
        "Dùng thanh công cụ editor để in đậm, nghiêng, đổi cỡ chữ."
    )

    edited_html = st_quill(
        value=article.get("article_html") or "",
        html=True,
        toolbar=[
            [{"header": [1, 2, 3, False]}],
            [{"size": ["small", False, "large", "huge"]}],
            ["bold", "italic", "underline", "strike"],
            [{"color": []}, {"background": []}],
            [{"list": "ordered"}, {"list": "bullet"}],
            ["link"],
            ["clean"],
        ],
        key=f"proj_quill_{project_id}",
    )

    save_col, copy_col = st.columns([1, 1])
    with save_col:
        if st.button(
            "Lưu bài viết",
            type="primary",
            use_container_width=True,
            key=f"proj_save_article_{project_id}",
        ):
            save_article(project_id, edited_html or "")
            st.success("Đã lưu bài viết (giữ format HTML).")
            st.rerun()
    with copy_col:
        body = edited_html or article.get("article_html") or ""
        _clipboard_copy_button(
            label="Copy bài viết",
            plain=html_to_plain(body),
            html_content=body,
            key=f"article_txt_{project_id}",
            height=52,
        )

    if body := (edited_html or article.get("article_html") or "").strip():
        with st.expander("Xem trước bài viết", expanded=False):
            st.markdown(
                f'<div class="pl-article-preview">{body}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("**Ảnh đính kèm**")
    uploads = st.file_uploader(
        "Upload ảnh",
        type=["png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=True,
        key=f"proj_article_upload_{project_id}",
    )
    if uploads and st.button(
        f"Lưu {len(uploads)} ảnh lên",
        key=f"proj_article_upload_save_{project_id}",
    ):
        for f in uploads:
            add_article_image(
                project_id,
                file_bytes=f.getvalue(),
                original_name=f.name or "image.jpg",
            )
        st.success(f"Đã upload {len(uploads)} ảnh.")
        st.rerun()

    images = list_article_images(project_id)
    if not images:
        st.caption("Chưa có ảnh — upload ở phía trên.")
        return

    for img in images:
        cols = st.columns([2.2, 1, 1])
        with cols[0]:
            if img.get("exists"):
                st.image(img["abs_path"], use_container_width=True, caption=img.get("original_name"))
            else:
                st.warning(f"Thiếu file: {img.get('rel_path')}")
        with cols[1]:
            uri = image_data_uri(img["abs_path"]) if img.get("exists") else None
            if uri:
                _clipboard_copy_button(
                    label="Copy ảnh",
                    image_data_uri_value=uri,
                    key=f"img_{img['id']}",
                    height=52,
                )
            else:
                st.caption("Không copy được")
        with cols[2]:
            if st.button(
                "Xóa ảnh",
                key=f"proj_del_img_{img['id']}",
                use_container_width=True,
            ):
                delete_article_image(int(img["id"]))
                st.rerun()


def _ensure_proj_state() -> None:
    if "proj_view" not in st.session_state:
        st.session_state.proj_view = "list"  # list | detail
    if "proj_detail_id" not in st.session_state:
        st.session_state.proj_detail_id = None


def _open_project_detail(project_id: int) -> None:
    st.session_state.proj_view = "detail"
    st.session_state.proj_detail_id = int(project_id)


def _back_to_project_list() -> None:
    st.session_state.proj_view = "list"
    st.session_state.proj_detail_id = None


def _inject_styles() -> None:
    st.markdown(
        """
<style>
.pl-proj-card {
  background: rgba(255,250,252,0.92);
  border: 1px solid rgba(232,145,176,0.35);
  border-radius: 18px;
  box-shadow: 0 10px 28px rgba(212,106,146,0.12);
  padding: 1rem 1.1rem 0.85rem;
  margin-bottom: 0.35rem;
}
.pl-proj-card-top {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: flex-start;
  margin-bottom: 0.85rem;
}
.pl-proj-title {
  font-family: "Playfair Display", Georgia, serif;
  color: #5c3a4a;
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.3;
}
.pl-proj-code {
  color: #8a6574;
  font-size: 0.85rem;
  margin-top: 0.25rem;
}
.pl-proj-badge {
  background: #f0a0be;
  color: #fff;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.28rem 0.55rem;
  border-radius: 0 12px 0 12px;
  white-space: nowrap;
}
.pl-proj-badge--expired { background: #9a7a86; }
.pl-proj-stats {
  display: grid;
  grid-template-columns: 1fr 1fr 1.2fr;
  gap: 0.65rem;
  margin-bottom: 0.75rem;
}
.pl-proj-stat-label {
  font-size: 0.75rem;
  color: #8a6574;
  margin-bottom: 0.2rem;
}
.pl-proj-pill {
  display: inline-block;
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.86rem;
  font-weight: 700;
}
.pl-proj-pill--start { background: #e8f3ff; color: #3a5a7a; }
.pl-proj-pill--end { background: #ffe8f0; color: #a0456a; }
.pl-proj-progress {
  height: 8px;
  background: #efe4e9;
  border-radius: 999px;
  overflow: hidden;
  margin: 0.35rem 0 0.15rem;
}
.pl-proj-progress > span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #f0a0be, #e27aa5);
}
.pl-proj-members, .pl-proj-link {
  font-size: 0.86rem;
  color: #5c3a4a;
  margin-top: 0.35rem;
}
.pl-proj-link { color: #8a6574; }
.pl-proj-section {
  background: rgba(255,250,252,0.88);
  border: 1px solid rgba(232,145,176,0.32);
  border-radius: 18px;
  padding: 1.1rem 1.2rem 1rem;
  margin-bottom: 1rem;
  box-shadow: 0 8px 22px rgba(212,106,146,0.08);
}
.pl-proj-section h3 {
  margin: 0 0 0.35rem 0 !important;
  font-family: "Playfair Display", Georgia, serif !important;
  color: #d46a92 !important;
  font-size: 1.25rem !important;
}
.pl-proj-section-desc {
  color: #8a6574;
  font-size: 0.9rem;
  margin: 0 0 0.85rem 0;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_project_card(project: dict) -> None:
    pid = int(project["project_id"])
    name = project.get("project_name") or f"Project {pid}"
    code = project.get("project_code") or "—"
    expired = int(project.get("is_expired") or 0)
    pct = int(project.get("total_percent_target") or 0)
    type_label = project_type_label(project.get("project_type"))
    start_s = format_display_date(
        project.get("start_date"), project.get("start_date_raw")
    )
    end_s = format_display_date(project.get("end_date"), project.get("end_date_raw"))
    link = (project.get("link_apply") or "").strip()
    link_chip = "Có link" if link else "Chưa có link"
    badge = "Hết hạn" if expired else type_label
    members_html = _esc(APP_USER_FULL_NAME)
    pct_clamped = max(0, min(100, pct))

    st.markdown(
        f"""
<div class="pl-proj-card">
  <div class="pl-proj-card-top">
    <div>
      <div class="pl-proj-title">{_esc(name)}</div>
      <div class="pl-proj-code">Mã dự án: {_esc(code)} · ID {pid}</div>
    </div>
    <span class="pl-proj-badge {'pl-proj-badge--expired' if expired else ''}">{_esc(badge)}</span>
  </div>
  <div class="pl-proj-stats">
    <div>
      <div class="pl-proj-stat-label">Ngày bắt đầu</div>
      <div class="pl-proj-pill pl-proj-pill--start">{_esc(start_s)}</div>
    </div>
    <div>
      <div class="pl-proj-stat-label">Ngày kết thúc</div>
      <div class="pl-proj-pill pl-proj-pill--end">{_esc(end_s)}</div>
    </div>
    <div>
      <div class="pl-proj-stat-label">Tiến độ</div>
      <div class="pl-proj-progress"><span style="width:{pct_clamped}%"></span></div>
      <div class="pl-proj-stat-label">{pct_clamped}%</div>
    </div>
  </div>
  <div class="pl-proj-members"><b>Thành viên:</b> {members_html}</div>
  <div class="pl-proj-link">{_esc(link_chip)}{' · ' + _esc(link[:64]) + ('…' if len(link) > 64 else '') if link else ''}</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Xem chi tiết", key=f"proj_detail_{pid}", use_container_width=True):
        _open_project_detail(pid)
        st.rerun()


def _render_project_detail_page(project_id: int) -> None:
    project = get_project(project_id)
    if project is None:
        st.error(f"Không thấy project #{project_id}")
        if st.button("← Về danh sách Projects"):
            _back_to_project_list()
            st.rerun()
        return

    code = project.get("project_code") or "—"
    name = project.get("project_name") or f"Project {project_id}"
    expired = int(project.get("is_expired") or 0)
    pct = project.get("total_percent_target")
    finished = project.get("master_finished_person")
    total = project.get("master_total_person")

    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.markdown(f"### {name}")
        st.caption(
            f"Mã: `{code}` · ID: `{project_id}` · "
            f"{'Hết hạn' if expired else 'Đang chạy'} · "
            f"{project_type_label(project.get('project_type'))}"
        )
    with top_r:
        if st.button("← Về danh sách", use_container_width=True, key="proj_back_list"):
            _back_to_project_list()
            st.rerun()

    # —— 1. Thông tin dự án + Link Apply ——
    st.markdown(
        """
<div class="pl-proj-section">
  <h3>1. Thông tin dự án &amp; Link Apply</h3>
  <p class="pl-proj-section-desc">
    Thông tin sync từ portal và link dùng khi đẩy ứng viên.
  </p>
</div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Ngày bắt đầu",
        format_display_date(project.get("start_date"), project.get("start_date_raw")),
    )
    c2.metric(
        "Ngày kết thúc",
        format_display_date(project.get("end_date"), project.get("end_date_raw")),
    )
    c3.metric("Tiến độ", f"{pct if pct is not None else 0}%")
    c4.metric(
        "Headcount",
        f"{finished if finished is not None else '—'} / "
        f"{total if total is not None else '—'}",
    )
    st.caption(f"Synced: `{project.get('synced_at') or '—'}`")

    st.markdown("**Link Apply**")
    st.caption(
        "Dạng: `…/ProjectHeadcount/ApplyRequest/xxxx` — "
        "bắt buộc có trước khi đẩy ứng viên cho project này."
    )
    with st.form(f"proj_link_form_{project_id}"):
        link = st.text_input(
            "Link Apply",
            value=project.get("link_apply") or "",
            placeholder=(
                "https://recruit.peoplelinkvietnam.com/"
                "ProjectHeadcount/ApplyRequest/2239"
            ),
        )
        saved = st.form_submit_button("Lưu Link Apply", type="primary")
    if saved:
        try:
            update_project_link_apply(project_id, link)
            st.success("Đã lưu Link Apply.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    raw = project.get("raw_json") or ""
    if raw:
        with st.expander("Raw JSON (portal)"):
            try:
                st.json(json.loads(raw))
            except json.JSONDecodeError:
                st.code(raw[:4000])

    st.divider()

    # —— 2. Bài viết ——
    _render_article_section(project_id)

    st.divider()

    # —— 3. Ứng viên đã submit ——
    submitted = list_submitted_for_project(project_id)
    st.markdown(
        f"""
<div class="pl-proj-section">
  <h3>3. Ứng viên đã submit</h3>
  <p class="pl-proj-section-desc">
    Tên + SĐT đã đẩy thành công vào project này
    ({len(submitted)} người). Dữ liệu giữ khi xóa batch.
  </p>
</div>
        """,
        unsafe_allow_html=True,
    )
    if not submitted:
        st.info("Chưa có ứng viên nào submit thành công cho project này.")
    else:
        q_key = f"proj_sub_q_{project_id}"
        go_key = f"proj_sub_go_{project_id}"
        active_key = f"proj_sub_active_{project_id}"
        if active_key not in st.session_state:
            st.session_state[active_key] = ""

        s1, s2 = st.columns([3.2, 1])
        with s1:
            query_input = st.text_input(
                "Tìm theo tên hoặc SĐT",
                placeholder="Nhập tên / số điện thoại…",
                key=q_key,
                label_visibility="collapsed",
            )
        with s2:
            if st.button("Search", use_container_width=True, key=go_key, type="primary"):
                st.session_state[active_key] = (query_input or "").strip()
                st.rerun()

        active_q = (st.session_state.get(active_key) or "").strip()
        rows = submitted
        if active_q:
            needle = active_q.casefold()
            needle_digits = "".join(ch for ch in active_q if ch.isdigit())
            filtered = []
            for r in submitted:
                name = str(r.get("full_name") or "")
                mobile = str(r.get("mobile") or "")
                if needle in name.casefold():
                    filtered.append(r)
                    continue
                if needle_digits and needle_digits in "".join(
                    ch for ch in mobile if ch.isdigit()
                ):
                    filtered.append(r)
            rows = filtered
            c_a, c_b = st.columns([3, 1])
            with c_a:
                st.caption(
                    f"Kết quả: **{len(rows)}** / {len(submitted)} · từ khóa `{active_q}`"
                )
            with c_b:
                if st.button("Xóa lọc", key=f"proj_sub_clear_{project_id}"):
                    st.session_state[active_key] = ""
                    st.session_state[q_key] = ""
                    st.rerun()

        frame = pd.DataFrame(
            [
                {
                    "Họ tên": r.get("full_name") or "",
                    "SĐT": r.get("mobile") or "",
                    "Submitted at": r.get("submitted_at") or "",
                }
                for r in rows
            ]
        )
        st.dataframe(
            frame,
            use_container_width=True,
            hide_index=True,
            height=360,
        )


def _render_project_list() -> None:
    st.subheader("Projects")
    st.caption(
        "Sync từ portal → xem thẻ → **Xem chi tiết** để điền Link Apply "
        "và xem ứng viên đã submit."
    )

    if "portal_cookie" not in st.session_state:
        st.session_state.portal_cookie = ""

    with st.expander("Portal cookie (Sync Projects)", expanded=False):
        st.text_area(
            "Cookie",
            height=72,
            placeholder="ASP.NET_SessionId=...; _ga=...",
            key="portal_cookie",
            label_visibility="collapsed",
        )

    col_a, col_b, col_c = st.columns(3)
    stats = db_stats()
    with col_a:
        st.metric("Projects (DB)", stats.get("projects", 0))
    with col_b:
        st.metric("Expired", stats.get("projects_expired", 0))
    with col_c:
        st.metric("Members", stats.get("project_members", 0))

    b1, b2 = st.columns(2)
    with b1:
        sync_clicked = st.button(
            "Sync Projects",
            type="primary",
            use_container_width=True,
            key="btn_sync_proj",
        )
    with b2:
        expire_clicked = st.button(
            "Đánh dấu project hết hạn",
            use_container_width=True,
            key="btn_mark_expired",
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
            f"tổng expired: {result.project_count}"
        )
        st.rerun()

    projects = list_projects_for_user(include_expired=True)
    st.write(f"Projects gắn user: **{len(projects)}**")
    if not projects:
        st.info("Chưa có project — Sync Projects với cookie portal trước.")
        return

    show_expired = st.checkbox("Hiện project hết hạn", value=True, key="proj_show_exp")
    visible = (
        projects
        if show_expired
        else [p for p in projects if not int(p.get("is_expired") or 0)]
    )

    for i in range(0, len(visible), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(visible):
                break
            with col:
                _render_project_card(visible[idx])


def render_projects_workspace() -> None:
    _ensure_proj_state()
    _inject_styles()

    if (
        st.session_state.proj_view == "detail"
        and st.session_state.proj_detail_id is not None
    ):
        _render_project_detail_page(int(st.session_state.proj_detail_id))
    else:
        _render_project_list()
