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

def page_dashboard(cfg: dict[str, Any]) -> None:
    header("决策看板", "重点机会优先，仓位动作次之")
    c1, c2 = st.columns([4, 1])
    with c1:
        force = st.checkbox("忽略缓存，获取最新数据", value=False, key="dash_force")
    with c2:
        go = st.button("刷新", type="primary", width="stretch")

    if go:
        st.session_state.pop("dash_snap", None)
        st.session_state.pop("_dash_load_failed", None)
        st.session_state.pop("_load_error", None)
        st.session_state["_isolated_load"] = {"kind": "dashboard", "force": True}
        st.rerun()

    suppress = st.session_state.pop("_suppress_autoload", False)
    if "dash_snap" not in st.session_state:
        if st.session_state.get("_dash_load_failed"):
            st.error(f"看板加载失败：{st.session_state.get('_load_error') or '未知错误'}")
            if st.button("重试加载看板", key="dash_retry"):
                st.session_state.pop("_dash_load_failed", None)
                st.session_state.pop("_load_error", None)
                st.session_state["_isolated_load"] = {"kind": "dashboard", "force": True}
                st.rerun()
            return
        if suppress:
            st.warning("看板数据未就绪")
            return
        st.session_state["_isolated_load"] = {"kind": "dashboard", "force": bool(force)}
        st.rerun()

    snap = st.session_state.dash_snap
    if snap.opportunities and not hasattr(snap.opportunities[0], "probability_up"):
        st.session_state.pop("dash_snap", None)
        st.session_state.pop("_dash_load_failed", None)
        st.session_state["_isolated_load"] = {"kind": "dashboard", "force": False}
        st.rerun()

    temp = "—" if snap.market_temperature is None else f"{snap.market_temperature:.0f}%"
    buy = sum(1 for a in snap.advices if a.action == "增持")
    sell = sum(1 for a in snap.advices if a.action == "减持")
    top = snap.opportunities[0] if snap.opportunities else None
    top_text = "—" if top is None else f"{top.index}"
    top_hint = "暂无排名" if top is None else f"{top.probability_up:.0%} · {top.bias}"
    if snap.macro is not None:
        macro_value = snap.macro.stance
        macro_hint = f"宏观 {snap.macro.macro_score:.0f} · 政策 {snap.macro.policy_score:.0f}"
    else:
        macro_value = "—"
        macro_hint = snap.market_label

    st.markdown(
        f"""
<div class="metric-strip">
  <div class="metric-item"><div class="label">市场温度</div><div class="value">{temp}</div><div class="hint">{escape(snap.market_label)}</div></div>
  <div class="metric-item"><div class="label">宏观 / 政策</div><div class="value">{escape(str(macro_value))}</div><div class="hint">{escape(macro_hint)}</div></div>
  <div class="metric-item"><div class="label">首位机会</div><div class="value">{escape(top_text)}</div><div class="hint">{escape(top_hint)}</div></div>
  <div class="metric-item"><div class="label">仓位动作</div><div class="value">{buy}↑ {sell}↓</div><div class="hint">总资产 ¥{snap.total_assets:,.0f}</div></div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        section_title("重点机会")
        render_opportunity_list(snap.opportunities, snap.opportunity_horizon)

    left, right = st.columns([1.25, 1], gap="large")
    with left:
        with st.container(border=True):
            section_title("建议仓位变化")
            if not snap.advices:
                st.info("暂无仓位建议")
            else:
                position_change_list(snap.advices, snap.explanations)

    with right:
        with st.container(border=True):
            section_title("观察池评分")
            if snap.ai_scores:
                score_df = pd.DataFrame(
                    [{"指数": s.index, "总分": s.total, "判断": s.label} for s in snap.ai_scores]
                )
                st.dataframe(
                    score_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "总分": st.column_config.ProgressColumn("总分", min_value=0, max_value=100)
                    },
                )
            else:
                st.caption("暂无观察指数评分")

            if snap.holdings_exposure:
                with st.expander("当前持仓"):
                    exp_df = pd.DataFrame(
                        [
                            {
                                "指数": k,
                                "金额": round(v["amount"], 2),
                                "仓位%": round(v["weight_pct"], 1),
                            }
                            for k, v in snap.holdings_exposure.items()
                        ]
                    )
                    st.dataframe(exp_df, width="stretch", hide_index=True)
            else:
                with st.expander("当前持仓"):
                    st.caption("尚未配置持仓")

            with st.expander("八因子与宏观明细"):
                if snap.ai_scores:
                    active_weights = get_scoring_settings(cfg)["weights"]
                    detail_df = pd.DataFrame(
                        [
                            {
                                "指数": s.index,
                                "估值": s.valuation,
                                "趋势": s.trend,
                                "资金": s.capital,
                                "盈利": s.earnings,
                                "风险": s.risk,
                                "情绪": s.sentiment,
                                "宏观": s.macro,
                                "政策": s.policy,
                            }
                            for s in snap.ai_scores
                        ]
                    )
                    st.dataframe(detail_df, width="stretch", hide_index=True)
                    st.caption(
                        "权重："
                        + " · ".join(f"{key} {value * 100:.0f}%" for key, value in active_weights.items())
                    )
                if snap.macro is not None:
                    m = snap.macro
                    st.caption(
                        f"PMI {m.pmi if m.pmi is not None else '—'} · "
                        f"CPI {m.cpi if m.cpi is not None else '—'}% · "
                        f"M2 {m.m2_yoy if m.m2_yoy is not None else '—'}% · "
                        f"LPR1Y {m.lpr_1y if m.lpr_1y is not None else '—'}%"
                    )


