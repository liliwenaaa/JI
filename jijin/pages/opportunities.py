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

def page_opportunities(cfg: dict[str, Any]) -> None:
    header(
        "重点机会",
        "扫描宽基 + 行业/主题指数，按策略参数上涨概率排出前列（不是基金筛选）",
    )
    trend_cfg = get_trend_settings(cfg)
    horizon = str(trend_cfg.get("default_horizon") or "1m")
    horizon_label = {
        "1d": "未来1天",
        "1w": "未来1周",
        "1m": "未来1个月",
        "3m": "未来3个月",
        "6m": "未来6个月",
        "1y": "未来1年",
    }.get(horizon, horizon)
    default_group = str((cfg.get("opportunity") or {}).get("universe_group") or "全部")
    if default_group not in INDEX_GROUP_OPTIONS:
        default_group = "全部"

    g1, g2, g3 = st.columns([2, 3, 1])
    with g1:
        group = st.selectbox(
            "指数分组",
            INDEX_GROUP_OPTIONS,
            index=INDEX_GROUP_OPTIONS.index(default_group),
            key="opp_group",
        )
    with g2:
        force = st.checkbox("忽略缓存，获取最新行情", value=False, key="opp_force")
        universe = market_index_universe(cfg, group=None if group == "全部" else group)
        st.caption(
            f"扫描 {len(universe)} 个指数 · 展望 {horizon_label} · 排名看上涨概率"
        )
    with g3:
        refresh = st.button("刷新机会", type="primary", width="stretch")

    # 临时覆盖分组，供 opportunity_agent / scan 读取
    run_cfg = dict(cfg)
    run_cfg["opportunity"] = {
        **dict(cfg.get("opportunity") or {}),
        "universe_group": None if group == "全部" else group,
        "top_n": int((cfg.get("opportunity") or {}).get("top_n") or 15),
    }

    cache_key = (horizon, group, len(universe))
    suppress = st.session_state.pop("_suppress_autoload", False)
    need_refresh = bool(refresh)
    if not suppress and not need_refresh:
        need_refresh = (
            "opp_list" not in st.session_state
            or st.session_state.get("opp_cache_key") != cache_key
        )
    elif suppress and "opp_list" in st.session_state:
        # 同轮刚加载完：对齐 cache_key，避免立刻又判定未命中
        st.session_state.opp_cache_key = cache_key
    if need_refresh:
        if (
            "opp_list" not in st.session_state
            and st.session_state.get("_opp_load_failed")
            and not refresh
        ):
            st.error(f"重点机会加载失败：{st.session_state.get('_load_error') or '未知错误'}")
            if st.button("重试扫描", key="opp_retry"):
                st.session_state.pop("_opp_load_failed", None)
                st.session_state.pop("_load_error", None)
                st.session_state["_isolated_load"] = {
                    "kind": "opportunity",
                    "force": True,
                    "group": group,
                    "cache_key": cache_key,
                    "top_n": run_cfg["opportunity"]["top_n"],
                }
                st.rerun()
            return
        if refresh:
            st.session_state.pop("_opp_load_failed", None)
        st.session_state["_isolated_load"] = {
            "kind": "opportunity",
            "force": bool(force or refresh),
            "group": group,
            "cache_key": cache_key,
            "top_n": run_cfg["opportunity"]["top_n"],
        }
        st.rerun()

    items = st.session_state.get("opp_list") or []
    scan_errors = opportunity_scan_errors(items)
    if scan_errors:
        with st.expander(f"部分指数扫描失败（{len(scan_errors)}）", expanded=False):
            st.caption("；".join(scan_errors[:12]))
    real_items = [x for x in items if not (x.details or {}).get("empty")]
    if not real_items:
        st.warning("暂无结果，请检查行情数据或稍后重试")
        return

    fetched = st.session_state.get("opp_fetched_at")
    section_title(f"上涨概率 Top {len(real_items)} · {real_items[0].horizon_label}")
    if fetched:
        st.caption(f"数据更新于 {fetched}")
    df = pd.DataFrame(opportunities_to_rows(real_items))
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "上涨概率": st.column_config.ProgressColumn(
                "上涨概率", min_value=0, max_value=1, format="percent"
            ),
            "趋势分": st.column_config.ProgressColumn("趋势分", min_value=0, max_value=100),
        },
        height=min(520, 56 + 34 * len(real_items)),
    )

    with st.expander("扫描宇宙（市场指数）"):
        by_group: dict[str, list[str]] = {}
        from jijin.data.market import index_group_of

        for name in universe:
            by_group.setdefault(index_group_of(name), []).append(name)
        for gname, names in by_group.items():
            st.markdown(f"**{gname}**（{len(names)}）")
            st.caption("、".join(names))
        st.caption("决策口径来自「策略参数」；估值百分位暂主要覆盖宽基观察池。")

    st.download_button(
        "导出结果 CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        "ai_index_opportunities.csv",
        "text/csv",
    )


