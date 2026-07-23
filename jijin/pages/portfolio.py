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

def page_portfolio_smart(cfg: dict[str, Any]) -> None:
    header("智能仓位", "输入风险偏好和资金，生成可执行的配置方案")
    with st.form("pos_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            risk = st.selectbox("风险偏好", list(RISK_PROFILES.keys()), index=1)
        with c2:
            template = st.selectbox(
                "策略模板",
                list(STRATEGY_TEMPLATES.keys()),
                format_func=lambda k: STRATEGY_TEMPLATES[k]["label"],
            )
        with c3:
            assets = st.number_input(
                "总资产",
                0.0,
                value=float((cfg.get("portfolio") or {}).get("total_assets") or 100000),
                step=1000.0,
            )
        with c4:
            monthly = st.number_input("月定投", 0.0, value=3000.0, step=100.0)
        sync_holdings = st.checkbox("同步到真实持仓（按目标仓位写入基金明细）", value=False)
        ok = st.form_submit_button("生成仓位方案", type="primary", width="stretch")

    if ok:
        with st.spinner("Portfolio Agent 计算中…"):
            plan = portfolio_agent(risk=risk, template=template, monthly_dca=monthly, cfg=cfg)
            plan.total_assets = assets
            st.session_state.plan = plan
            if sync_holdings:
                pf = dict(cfg.get("portfolio") or {})
                existing = list(pf.get("holdings") or [])
                rows = apply_strategy_to_holdings(
                    total_assets=float(assets),
                    sleeves=plan.sleeves,
                    existing=existing,
                )
                watch = list((cfg.get("valuation") or {}).get("watch_indexes") or [])
                for s in plan.sleeves:
                    if s.index and s.index not in watch:
                        watch.append(s.index)
                cfg["portfolio"] = {
                    **pf,
                    "total_assets": float(assets),
                    "holdings": rows,
                }
                # 不再维护计划仓位
                cfg["portfolio"].pop("index_plans", None)
                cfg.setdefault("valuation", {})["watch_indexes"] = watch
                save_config(cfg)
                st.session_state.cfg = load_config()
                st.session_state.pop("dash_snap", None)
                st.session_state.pop("_hold_cfg_stamp", None)
                st.session_state.hold_info_msg = f"已同步 {len(rows)} 条持仓到配置"

    plan = st.session_state.get("plan")
    if not plan:
        st.info("生成后将展示目标仓位与推荐基金；勾选「同步到真实持仓」可写入持仓页")
        return
    st.success(plan.summary)
    m1, m2, m3 = st.columns(3)
    m1.metric("权益目标", f"{plan.equity_ratio:.1f}%")
    m2.metric("现金/债缓冲", f"{plan.cash_bond_ratio:.1f}%")
    m3.metric("月定投", f"{plan.monthly_dca:,.0f}")
    st.dataframe(plan.to_dataframe(), width="stretch", hide_index=True)
    st.bar_chart(plan.to_dataframe().set_index("指数")[["基准仓位%", "目标仓位%"]], height=260)
    st.markdown("#### 执行规则")
    for r in plan.rules:
        st.write(f"- {r}")
    st.download_button("下载策略 Markdown", plan.to_markdown().encode("utf-8"), "ai_index_strategy.md")


