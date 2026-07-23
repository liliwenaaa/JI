from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from html import escape
import json
import re
from typing import Any, Callable, Iterator

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from jijin.agents import (
    build_dashboard,
    calibrate_agent,
    coach_agent,
    opportunity_agent,
    portfolio_agent,
    score_agent,
    trend_horizons_agent,
)
from jijin.alert.smart import generate_smart_alerts
from jijin.config import cache_dir, load_config, save_config, to_yaml_safe
from jijin.data.cache import CacheStore
from jijin.data.fund import lookup_fund_by_code
from jijin.data.market import INDEX_GROUPS, INDEX_SYMBOLS
from jijin.portfolio.holdings import apply_strategy_to_holdings
from jijin.engine.settings import (
    DEFAULT_MACRO_SETTINGS,
    DEFAULT_SCORING_SETTINGS,
    DEFAULT_TREND_SETTINGS,
    get_macro_settings,
    get_scoring_settings,
    get_trend_settings,
    list_trend_horizons,
)
from jijin.screener.opportunity import (
    market_index_universe,
    opportunities_to_rows,
    opportunity_scan_errors,
)
from jijin.strategy.generator import RISK_PROFILES, STRATEGY_TEMPLATES

from jijin.ui.constants import INDEX_GROUP_OPTIONS, INDEX_OPTIONS, score_cache_key
from jijin.ui.widgets import (
    header,
    panel_hint,
    position_change_list,
    render_horizon_line_chart,
    render_opportunity_list,
    render_trend_matrix,
    section_title,
)
from jijin.ui.state import (
    _enrich_holding_rows,
    _holdings_records,
    _invalidate_analysis_state,
    _sync_holdings_editor_state,
    get_cfg,
)
from jijin.ui.loading import (
    _compute_score_payload,
    loading_progress,
)

def page_alerts(cfg: dict[str, Any]) -> None:
    header("智能提醒", "只关注需要处理的变化")
    c1, c2 = st.columns([4, 1])
    with c1:
        force = st.checkbox("忽略缓存，获取最新数据", value=False, key="alert_force")
    with c2:
        refresh = st.button("刷新提醒", type="primary", width="stretch")
    if refresh:
        st.session_state.pop("smart_alerts", None)
        st.session_state.pop("_alert_load_failed", None)
        st.session_state.pop("alert_fetched_at", None)
    suppress = st.session_state.pop("_suppress_autoload", False)
    if "smart_alerts" not in st.session_state:
        if st.session_state.get("_alert_load_failed") and not refresh:
            st.error(f"智能提醒加载失败：{st.session_state.get('_load_error') or '未知错误'}")
            if st.button("重试提醒", key="alert_retry"):
                st.session_state.pop("_alert_load_failed", None)
                st.session_state.pop("_load_error", None)
                st.session_state["_isolated_load"] = {"kind": "alerts", "force": True}
                st.rerun()
            return
        if suppress:
            st.warning("提醒数据未就绪")
            return
        st.session_state["_isolated_load"] = {"kind": "alerts", "force": bool(force or refresh)}
        st.rerun()
    if st.session_state.get("alert_fetched_at"):
        st.caption(f"数据更新于 {st.session_state.alert_fetched_at}")

    alerts = st.session_state.smart_alerts
    action_count = sum(a.level == "action" for a in alerts)
    warn_count = sum(a.level == "warn" for a in alerts)
    info_count = sum(a.level == "info" for a in alerts)
    st.markdown(
        f"""
<div class="position-summary">
  <span><strong>{action_count}</strong> 项待执行</span>
  <span><strong>{warn_count}</strong> 项风险</span>
  <span>{info_count} 项观察</span>
</div>
        """,
        unsafe_allow_html=True,
    )

    cats = ["全部", "估值", "趋势", "风险", "再平衡", "定投"]
    cat = st.radio("类型", cats, horizontal=True)
    filtered = alerts if cat == "全部" else [a for a in alerts if a.category == cat]
    if not filtered:
        st.info("无提醒")
        return

    priority = {"action": 0, "warn": 1, "info": 2}
    filtered = sorted(filtered, key=lambda a: (priority.get(a.level, 3), a.category, a.index))
    important = [a for a in filtered if a.level in {"action", "warn"}]
    info_alerts = [a for a in filtered if a.level == "info"]
    if important:
        section_title("需要关注")
        rows = []
        for a in important:
            if a.current_pct is not None and a.target_pct is not None:
                delta = a.delta_pct if a.delta_pct is not None else a.target_pct - a.current_pct
                sign = "+" if delta > 0 else "−"
                detail = f"{a.current_pct:.1f}% → {a.target_pct:.1f}% · {sign}{abs(delta):.1f}pct"
            else:
                detail = a.message
            if a.action and a.amount is not None:
                value = f"{escape(a.action)} ¥{a.amount:,.0f}"
            elif a.level == "warn":
                value = "注意风险"
            else:
                value = escape(a.action or "待处理")
            rows.append(
                f"""
<div class="alert-row {escape(a.level)}">
  <div class="alert-category">{escape(a.category)}</div>
  <div class="alert-title">{escape(a.title)}</div>
  <div class="alert-detail" title="{escape(a.message)}">{escape(detail)}</div>
  <div class="alert-value">{value}</div>
</div>
                """
            )
        st.markdown(
            '<div class="alert-list">' + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )

    if info_alerts:
        with st.expander(f"观察信息（{len(info_alerts)}）", expanded=not important):
            info_df = pd.DataFrame(
                [
                    {
                        "类型": a.category,
                        "指数": a.index,
                        "提醒": a.title,
                        "说明": a.message,
                    }
                    for a in info_alerts
                ]
            )
            st.dataframe(info_df, width="stretch", hide_index=True, height=300)

    if important:
        with st.expander("查看完整提醒内容"):
            for a in important:
                st.markdown(f"**{a.title}**")
                st.write(a.message)


