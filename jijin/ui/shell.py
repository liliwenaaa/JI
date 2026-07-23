"""插件化 Streamlit Shell：缓存优先 + fragment 轮询，避免加载假死。"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import streamlit as st

from jijin.plugin import enabled_page_ids, load_plugins
from jijin.plugin.registry import registry
from jijin.ui.loading import _apply_load_payload, _render_loading_panel
from jijin.ui.state import _purge_ephemeral_ui_state, get_cfg
from jijin.ui.style import inject_style
from jijin.utils.bg_job import (
    bump_generation,
    drop_bg_job,
    get_bg_job,
    start_bg_job,
)
from jijin.utils.http_patch import install_requests_timeout

install_requests_timeout(12.0)

_SOFT_TIMEOUT = {
    "opportunity": 90.0,
    "dashboard": 100.0,
    "score": 55.0,
    "alerts": 55.0,
}
_HARD_TIMEOUT = {
    "opportunity": 110.0,
    "dashboard": 120.0,
    "score": 70.0,
    "alerts": 70.0,
}


def _resolve_job_page(job: dict[str, Any] | None) -> str | None:
    if not isinstance(job, dict):
        return None
    kind = str(job.get("kind") or "")
    spec = registry.page_by_load_kind(kind)
    return spec.title if spec else None


def _fail_key(kind: str) -> str | None:
    return {
        "dashboard": "_dash_load_failed",
        "opportunity": "_opp_load_failed",
        "score": "_score_load_failed",
        "alerts": "_alert_load_failed",
    }.get(kind)


def _apply_finished_job(bg: Any) -> None:
    snap = bg.snapshot()
    status = snap["status"]
    if status == "done":
        _apply_load_payload(dict(bg.result))
        st.session_state["_suppress_autoload"] = True
    elif status in {"error", "cancelled"}:
        st.session_state["_load_error"] = snap.get("error") or "加载失败"
        st.session_state["_suppress_autoload"] = True
        fk = _fail_key(str(bg.kind))
        if fk:
            st.session_state[fk] = True
    drop_bg_job(bg.id)
    st.session_state.pop("_bg_job_id", None)
    st.session_state.pop("_bg_page", None)
    st.session_state.pop("_bg_blocking", None)


def main() -> None:
    st.set_page_config(
        page_title="AI Index",
        page_icon="◎",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_style()
    cfg = get_cfg()
    load_plugins(cfg)

    page_ids = enabled_page_ids(cfg)
    pages = registry.sorted_pages(page_ids)
    titles = [p.title for p in pages]
    if not titles:
        st.error("没有启用的页面插件，请检查 config.plugins")
        return

    with st.sidebar:
        st.markdown(
            """
<div class="sidebar-brand">
  <div class="mark">◎</div>
  <h2>AI Index</h2>
  <p>指数基金决策助手<br>本地运行 · 数据不出本机</p>
</div>
            """,
            unsafe_allow_html=True,
        )
        current = st.session_state.get("nav_page")
        if current not in titles:
            st.session_state["nav_page"] = titles[0]
        page = st.radio(
            "导航",
            titles,
            label_visibility="collapsed",
            key="nav_page",
        )

    body = st.empty()
    page_spec = registry.page_by_title(page)
    if page_spec is None:
        st.error(f"未知页面: {page}")
        return

    page_changed = st.session_state.get("_nav_page") != page
    if page_changed:
        st.session_state._nav_page = page
        _purge_ephemeral_ui_state()
        bump_generation()
        old_id = st.session_state.pop("_bg_job_id", None)
        drop_bg_job(old_id)
        st.session_state.pop("_bg_page", None)
        st.session_state.pop("_bg_blocking", None)
        for k in ("_isolated_load", "_isolated_armed", "_boot_load", "_boot_clear", "_pending_page"):
            st.session_state.pop(k, None)

    job = st.session_state.get("_isolated_load")
    job_for_page = _resolve_job_page(job if isinstance(job, dict) else None) == page
    need_prefetch = page_changed and page_spec.needs_data_or_false(cfg)
    has_cache = not page_spec.needs_data_or_false(cfg)
    bg_id = st.session_state.get("_bg_job_id")
    bg = get_bg_job(bg_id)

    # 启动加载：无缓存时阻塞面板；有缓存时后台刷新，页面可先渲染
    if bg is None and (job_for_page or need_prefetch):
        active_job = st.session_state.pop("_isolated_load", None) if job_for_page else None
        built = page_spec.build_load_or_none(
            cfg, active_job if isinstance(active_job, dict) else None
        )
        if built is not None:
            kind, load_fn = built
            soft = _SOFT_TIMEOUT.get(kind, 60.0)
            hard = _HARD_TIMEOUT.get(kind, 90.0)
            # 无缓存：阻塞进度面板；有缓存的刷新：页面先渲染，后台更新
            blocking = not has_cache
            bg = start_bg_job(
                kind,
                load_fn,
                soft_timeout_sec=soft,
                hard_timeout_sec=hard,
            )
            st.session_state["_bg_job_id"] = bg.id
            st.session_state["_bg_page"] = page
            st.session_state["_bg_blocking"] = blocking

    blocking = bool(st.session_state.get("_bg_blocking", True))

    # 任务已结束：写入结果
    if bg is not None and st.session_state.get("_bg_page") == page:
        snap = bg.snapshot()
        if snap["status"] != "running":
            _apply_finished_job(bg)
            bg = None

    # 阻塞加载：只画进度，fragment 每秒刷新；到软超时立刻结束等待
    if (
        bg is not None
        and bg.status == "running"
        and st.session_state.get("_bg_page") == page
        and blocking
    ):
        soft = float(bg.soft_timeout_sec)

        @st.fragment(run_every=timedelta(seconds=1))
        def _poll_blocking() -> None:
            job_now = get_bg_job(st.session_state.get("_bg_job_id"))
            if job_now is None:
                st.rerun()
                return
            s = job_now.snapshot()
            if s["status"] == "running" and s["elapsed"] >= soft:
                job_now.mark_soft_timeout()
                st.rerun()
                return
            if s["status"] != "running":
                st.rerun()
                return
            _render_loading_panel(
                page,
                s["done"],
                s["total"],
                s["message"],
                s["elapsed"],
            )
            cols = st.columns([1, 1, 2])
            with cols[0]:
                if st.button("跳过等待", key=f"skip_wait_{job_now.id}"):
                    job_now.mark_soft_timeout()
                    st.rerun()
            with cols[1]:
                st.caption(f"软超时 {soft:.0f}s · 可切换左侧页面")

        with body.container():
            _poll_blocking()
        st.stop()

    # 非阻塞刷新：页面照常渲染，顶部提示
    refreshing = (
        bg is not None
        and bg.status == "running"
        and st.session_state.get("_bg_page") == page
        and not blocking
    )
    if refreshing:

        @st.fragment(run_every=timedelta(seconds=1))
        def _poll_soft() -> None:
            job_now = get_bg_job(st.session_state.get("_bg_job_id"))
            if job_now is None:
                return
            s = job_now.snapshot()
            if s["status"] == "running" and s["elapsed"] >= float(job_now.soft_timeout_sec):
                job_now.mark_soft_timeout()
                st.rerun()
                return
            if s["status"] != "running":
                st.rerun()
                return
            st.caption(
                f"后台刷新中 {s['done']}/{s['total']} · {s['message']} · {s['elapsed']:.0f}s"
            )

        _poll_soft()

    with body.container():
        if err := st.session_state.pop("_load_error", None):
            st.warning(f"加载未完成：{err}")
        page_spec.render(cfg)
        st.markdown(
            '<p class="disclaimer">AI Index 输出为概率化决策辅助，不构成投资建议。'
            "通知渠道（邮件/企微/Telegram）可在后续版本接入。</p>",
            unsafe_allow_html=True,
        )
