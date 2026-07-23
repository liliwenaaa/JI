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
    _normalize_trend_multi,
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
from jijin.ui.loading import _refresh_score_cache

def page_score(cfg: dict[str, Any]) -> None:
    active_weights = get_scoring_settings(cfg)["weights"]
    weight_text = " + ".join(
        f"{key}{value * 100:.0f}%"
        for key, value in active_weights.items()
    )
    header("评分与趋势", "自动刷新全部展望周期，一眼对比方向与强弱")
    indexes = cfg.get("valuation", {}).get("watch_indexes") or ["沪深300", "中证500"]
    pick = st.multiselect(
        "分析指数",
        options=list(dict.fromkeys(indexes + INDEX_OPTIONS)),
        default=list(indexes),
        key="score_pick",
    )
    default_horizon = get_trend_settings(cfg).get("default_horizon", "1m")
    c1, c2 = st.columns([4, 1])
    with c1:
        force = st.checkbox("忽略缓存，获取最新行情", value=False, key="score_force")
    with c2:
        manual_refresh = st.button("刷新", type="primary", width="stretch")

    if not pick:
        st.info("请至少选择一个指数")
        return

    cache_key = score_cache_key(list(pick), str(default_horizon))
    multi_existing = st.session_state.get("trend_multi") or {}
    suppress = st.session_state.pop("_suppress_autoload", False)
    need_refresh = bool(manual_refresh)
    if suppress and multi_existing:
        st.session_state.score_cache_key = cache_key
        need_refresh = False
    elif not need_refresh:
        if not multi_existing:
            # 已尝试过且全部失败：展示错误，禁止自动死循环重试
            if st.session_state.get("_score_load_failed") and st.session_state.get("score_cache_key") == cache_key:
                st.error("评分趋势加载失败：全部指数均无结果，请检查网络后重试")
                for w in st.session_state.get("score_load_warnings") or []:
                    st.caption(w)
                if st.button("重试评分", key="score_retry"):
                    st.session_state.pop("_score_load_failed", None)
                    st.session_state.pop("score_cache_key", None)
                    st.session_state.pop("trend_multi", None)
                    st.session_state["_isolated_load"] = {
                        "kind": "score",
                        "force": True,
                        "pick": list(pick),
                    }
                    st.rerun()
                return
            need_refresh = True
        elif st.session_state.get("score_cache_key") != cache_key:
            need_refresh = any(p not in multi_existing for p in pick)
        if not need_refresh and st.session_state.get("score_cache_key") != cache_key:
            st.session_state.score_cache_key = cache_key

    if need_refresh:
        st.session_state.pop("_score_load_failed", None)
        st.session_state["_isolated_load"] = {
            "kind": "score",
            "force": bool(force or manual_refresh),
            "pick": list(pick),
        }
        st.rerun()

    for w in st.session_state.pop("score_load_warnings", []) or []:
        st.warning(w)

    table = st.session_state.get("score_table")
    multi = st.session_state.get("trend_multi") or {}
    # 只展示当前选中的指数
    multi = {k: v for k, v in multi.items() if k in pick}
    if table is not None and not getattr(table, "empty", True) and "指数" in table.columns:
        table = table[table["指数"].isin(pick)].reset_index(drop=True)
    if not multi:
        st.warning("暂无趋势结果")
        return

    section_title("多周期趋势对比")
    st.caption("进入页面即自动刷新全部周期；红偏多、绿偏空、灰中性（A股红涨绿跌）。周期越长，方向置信度越向中性收缩。")
    multi = _normalize_trend_multi(multi)
    render_trend_matrix(multi)

    chart_tab, prob_tab, table_tab = st.tabs(["趋势分曲线", "偏多概率曲线", "明细表"])
    with chart_tab:
        st.caption("横轴按 1天 → 1周 → 1个月 → 3个月 → 6个月 → 1年 排列；越高越偏多（50 为中性）")
        render_horizon_line_chart(
            multi,
            value_attr="score",
            value_title="趋势分",
            y_domain=[0, 100],
        )
    with prob_tab:
        st.caption("偏多方向置信度；周期越长越向 50% 收缩")
        render_horizon_line_chart(
            multi,
            value_attr="probability_up",
            value_title="偏多概率",
            y_domain=[0, 1],
        )
    with table_tab:
        compare_rows = []
        for name, results in multi.items():
            for tr in results:
                compare_rows.append(
                    {
                        "指数": name,
                        "周期": tr.horizon_label,
                        "交易日": tr.horizon_days,
                        "方向": tr.bias,
                        "趋势分": tr.score,
                        "偏多概率": tr.probability_up,
                        "体制": (tr.details or {}).get("regime") or "—",
                        "强度": tr.strength,
                        "波动带宽%": tr.move_band_pct,
                        "风险": tr.risk_level,
                        "MA": tr.ma_signal,
                    }
                )
        compare_df = pd.DataFrame(compare_rows)
        if not compare_df.empty:
            compare_df = compare_df.sort_values(["指数", "交易日"], kind="mergesort")
        st.dataframe(
            compare_df.drop(columns=["交易日"], errors="ignore"),
            width="stretch",
            hide_index=True,
            column_config={
                "趋势分": st.column_config.ProgressColumn("趋势分", min_value=0, max_value=100),
                "偏多概率": st.column_config.ProgressColumn(
                    "偏多概率", min_value=0, max_value=1, format="percent"
                ),
            },
            height=min(460, 56 + 36 * len(compare_rows)),
        )

    if table is not None and not table.empty:
        section_title("AI 综合评分")
        core_columns = [
            "指数",
            "AI分",
            "标签",
            "参考展望",
            "方向",
            "趋势分",
            "体制",
            "Supertrend",
            "强度",
            "MTF",
            "偏多概率",
            "趋势风险",
        ]
        show_cols = [c for c in core_columns if c in table.columns]
        st.dataframe(
            table[show_cols],
            width="stretch",
            hide_index=True,
            column_config={
                "AI分": st.column_config.ProgressColumn("AI 分", min_value=0, max_value=100),
                "趋势分": st.column_config.ProgressColumn("趋势分", min_value=0, max_value=100),
                "偏多概率": st.column_config.ProgressColumn(
                    "偏多概率", min_value=0, max_value=1, format="percent"
                ),
            },
        )
        with st.expander("查看因子与技术指标明细"):
            st.caption(f"评分权重：{weight_text}")
            st.dataframe(table, width="stretch", hide_index=True)

    section_title("决策解释")
    for name in pick:
        exp = st.session_state.get(f"exp_{name}")
        if not exp:
            continue
        with st.expander(exp.title, expanded=False):
            st.write(exp.summary)
            cols = st.columns(3)
            with cols[0]:
                st.markdown("**为什么推荐**")
                for x in exp.why_recommend or ["—"]:
                    st.write(f"- {x}")
            with cols[1]:
                st.markdown("**为什么谨慎**")
                for x in exp.why_not or ["—"]:
                    st.write(f"- {x}")
            with cols[2]:
                st.markdown("**风险来源**")
                for x in exp.risk_sources or ["—"]:
                    st.write(f"- {x}")
            st.markdown("**历史/统计依据**")
            for x in exp.evidence or ["—"]:
                st.write(f"- {x}")


