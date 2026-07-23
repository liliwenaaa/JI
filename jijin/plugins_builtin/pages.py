"""内置页面插件：把 jijin.pages.* 挂到注册表。"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from jijin.agents import build_dashboard, opportunity_agent
from jijin.alert.smart import generate_smart_alerts
from jijin.engine.settings import get_trend_settings
from jijin.pages import alerts, dashboard, holdings, opportunities, parameters, portfolio, score
from jijin.plugin.base import LoadFn, PageSpec
from jijin.plugin.registry import PluginRegistry
from jijin.screener.opportunity import market_index_universe
from jijin.ui.constants import INDEX_GROUP_OPTIONS, score_cache_key
from jijin.ui.loading import _compute_score_payload

ProgressCb = Callable[[int, int, str], None]


def _needs_dashboard(cfg: dict[str, Any]) -> bool:
    return "dash_snap" not in st.session_state


def _load_dashboard(cfg: dict[str, Any], job: dict[str, Any] | None) -> tuple[str, LoadFn]:
    force = bool((job or {}).get("force"))
    # 在主线程捕获机会列表，供后台看板复用（避免再扫全市场）
    opp_reuse = None
    if not force:
        cached = st.session_state.get("opp_list")
        if cached:
            opp_reuse = cached

    def _fn(progress: ProgressCb) -> dict[str, Any]:
        snap = build_dashboard(
            cfg,
            force=force,
            on_progress=progress,
            opportunities=opp_reuse,
        )
        out: dict[str, Any] = {"dash_snap": snap}
        if job is not None:
            out["_dash_load_failed"] = False
        return out

    return "dashboard", _fn


def _needs_opportunity(cfg: dict[str, Any]) -> bool:
    trend_cfg = get_trend_settings(cfg)
    horizon = str(trend_cfg.get("default_horizon") or "1m")
    group = str(
        st.session_state.get("opp_group")
        or (cfg.get("opportunity") or {}).get("universe_group")
        or "全部"
    )
    if group not in INDEX_GROUP_OPTIONS:
        group = "全部"
    universe = market_index_universe(cfg, group=None if group == "全部" else group)
    cache_key = (horizon, group, len(universe))
    return "opp_list" not in st.session_state or st.session_state.get("opp_cache_key") != cache_key


def _load_opportunity(cfg: dict[str, Any], job: dict[str, Any] | None) -> tuple[str, LoadFn]:
    force = bool((job or {}).get("force"))
    if job:
        group = str(job.get("group") or "全部")
        cache_key = job.get("cache_key")
        top_n = int(job.get("top_n") or 15)
    else:
        trend_cfg = get_trend_settings(cfg)
        horizon = str(trend_cfg.get("default_horizon") or "1m")
        group = str(
            st.session_state.get("opp_group")
            or (cfg.get("opportunity") or {}).get("universe_group")
            or "全部"
        )
        if group not in INDEX_GROUP_OPTIONS:
            group = "全部"
        universe = market_index_universe(cfg, group=None if group == "全部" else group)
        cache_key = (horizon, group, len(universe))
        top_n = int((cfg.get("opportunity") or {}).get("top_n") or 15)

    run_cfg = dict(cfg)
    run_cfg["opportunity"] = {
        **dict(cfg.get("opportunity") or {}),
        "universe_group": None if group == "全部" else group,
        "top_n": top_n,
    }

    def _fn(progress: ProgressCb) -> dict[str, Any]:
        items = opportunity_agent(
            cfg=run_cfg,
            force=force,
            top_n=run_cfg["opportunity"]["top_n"],
            on_progress=progress,
        )
        out = {
            "opp_list": items,
            "opp_cache_key": cache_key,
            "opp_fetched_at": pd.Timestamp.now().strftime("%H:%M:%S"),
        }
        if job is not None:
            out["_opp_load_failed"] = False
        return out

    return "opportunity", _fn


def _needs_score(cfg: dict[str, Any]) -> bool:
    indexes = list(cfg.get("valuation", {}).get("watch_indexes") or ["沪深300", "中证500"])
    pick = list(st.session_state.get("score_pick") or indexes) or indexes
    default_horizon = get_trend_settings(cfg).get("default_horizon", "1m")
    cache_key = score_cache_key(pick, str(default_horizon))
    return "trend_multi" not in st.session_state or st.session_state.get("score_cache_key") != cache_key


def _load_score(cfg: dict[str, Any], job: dict[str, Any] | None) -> tuple[str, LoadFn]:
    force = bool((job or {}).get("force"))
    if job:
        pick = list(job.get("pick") or [])
    else:
        indexes = list(cfg.get("valuation", {}).get("watch_indexes") or ["沪深300", "中证500"])
        pick = list(st.session_state.get("score_pick") or indexes) or indexes

    def _fn(progress: ProgressCb) -> dict[str, Any]:
        return _compute_score_payload(cfg, pick, force, on_progress=progress)

    return "score", _fn


def _needs_alerts(cfg: dict[str, Any]) -> bool:
    _ = cfg
    return "smart_alerts" not in st.session_state


def _load_alerts(cfg: dict[str, Any], job: dict[str, Any] | None) -> tuple[str, LoadFn]:
    force = bool((job or {}).get("force"))

    def _fn(progress: ProgressCb) -> dict[str, Any]:
        alerts = generate_smart_alerts(cfg, force=force, on_progress=progress)
        out: dict[str, Any] = {
            "smart_alerts": alerts,
            "alert_fetched_at": pd.Timestamp.now().strftime("%H:%M:%S"),
        }
        if job is not None:
            out["_alert_load_failed"] = False
        return out

    return "alerts", _fn


def register(reg: PluginRegistry) -> None:
    pages = [
        PageSpec(
            id="dashboard",
            title="看板",
            order=10,
            render=dashboard.page_dashboard,
            needs_data=_needs_dashboard,
            build_load=_load_dashboard,
            load_kind="dashboard",
            description="决策看板",
        ),
        PageSpec(
            id="opportunity",
            title="重点机会",
            order=20,
            render=opportunities.page_opportunities,
            needs_data=_needs_opportunity,
            build_load=_load_opportunity,
            load_kind="opportunity",
            description="市场指数机会扫描",
        ),
        PageSpec(
            id="score",
            title="评分趋势",
            order=30,
            render=score.page_score,
            needs_data=_needs_score,
            build_load=_load_score,
            load_kind="score",
            description="评分与多周期趋势",
        ),
        PageSpec(
            id="portfolio",
            title="智能仓位",
            order=40,
            render=portfolio.page_portfolio_smart,
            description="策略仓位方案",
        ),
        PageSpec(
            id="alerts",
            title="智能提醒",
            order=50,
            render=alerts.page_alerts,
            needs_data=_needs_alerts,
            build_load=_load_alerts,
            load_kind="alerts",
            description="估值/趋势/再平衡提醒",
        ),
        PageSpec(
            id="holdings",
            title="持仓",
            order=60,
            render=holdings.page_holdings,
            description="真实持仓管理",
        ),
        PageSpec(
            id="parameters",
            title="策略参数",
            order=70,
            render=parameters.page_parameters,
            description="趋势/评分/宏观参数",
        ),
    ]
    for spec in pages:
        reg.register_page(spec, replace=True)
