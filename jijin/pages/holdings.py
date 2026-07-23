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
from jijin.ui.state import _clean_float, _clean_str, _is_blank

def page_holdings(cfg: dict[str, Any]) -> None:
    header("持仓配置", "管理真实持仓；可同步智能仓位策略建议")
    _sync_holdings_editor_state(cfg)
    if st.session_state.pop("hold_save_ok", False):
        st.success("已保存")
    if msg := st.session_state.pop("hold_info_msg", None):
        st.info(str(msg))

    ver = int(st.session_state.get("hold_ui_ver") or 0)
    pf = dict(cfg.get("portfolio") or {})

    if f"hold_total_assets_{ver}" not in st.session_state:
        st.session_state[f"hold_total_assets_{ver}"] = float(
            st.session_state.get("hold_total_assets_val")
            or pf.get("total_assets")
            or 0
        )
    total_assets = st.number_input(
        "总资产(元)",
        min_value=0.0,
        step=1000.0,
        key=f"hold_total_assets_{ver}",
    )

    # 当前真实仓位一览
    fund_preview = list(st.session_state.get("hold_fund_rows") or [])
    enabled_amt = sum(_clean_float(r.get("amount")) for r in fund_preview if bool(r.get("enabled", True)))
    denom = float(total_assets) if total_assets > 0 else (enabled_amt or 1.0)
    by_idx: dict[str, float] = {}
    for r in fund_preview:
        if not bool(r.get("enabled", True)):
            continue
        idx = _clean_str(r.get("index")) or "未分类"
        by_idx[idx] = by_idx.get(idx, 0.0) + _clean_float(r.get("amount"))
    if by_idx:
        st.markdown("#### 当前仓位")
        exp_df = pd.DataFrame(
            [
                {"指数": k, "金额(元)": round(v, 2), "仓位%": round(v / denom * 100, 2)}
                for k, v in sorted(by_idx.items(), key=lambda x: -x[1])
            ]
        )
        st.dataframe(exp_df, width="stretch", hide_index=True)
        st.caption(f"已启用持仓合计 ¥{enabled_amt:,.0f} / 总资产 ¥{float(total_assets):,.0f}")

    st.markdown("#### 观察指数")
    st.multiselect(
        "看板评分 / 提醒会跟踪这些指数（无持仓时仅观察，不生成加减仓）",
        options=INDEX_OPTIONS,
        key="hold_watch_multiselect",
    )

    st.markdown("#### 基金明细")
    st.caption("维护真实持仓；填写代码后可「按代码补全」。也可从「智能仓位」同步策略建议。")
    fund_rows = list(st.session_state.get("hold_fund_rows") or [])
    hold_df = pd.DataFrame(fund_rows) if fund_rows else pd.DataFrame(
        columns=["code", "name", "amount", "index", "enabled", "删除"]
    )
    for col in ["code", "name", "amount", "index", "enabled", "删除"]:
        if col not in hold_df.columns:
            if col == "enabled":
                hold_df[col] = True
            elif col == "删除":
                hold_df[col] = False
            elif col == "amount":
                hold_df[col] = 0.0
            else:
                hold_df[col] = ""
    hold_df = hold_df.copy()
    hold_df["code"] = hold_df["code"].map(_clean_str)
    hold_df["name"] = hold_df["name"].map(_clean_str)
    hold_df["index"] = hold_df["index"].map(_clean_str)
    hold_df["amount"] = hold_df["amount"].map(lambda x: _clean_float(x))
    hold_df["enabled"] = hold_df["enabled"].map(lambda x: bool(x) if not _is_blank(x) else True)
    hold_df["删除"] = hold_df["删除"].map(lambda x: bool(x) if not _is_blank(x) else False)

    edited = st.data_editor(
        hold_df[["code", "name", "amount", "index", "enabled", "删除"]],
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        height=280,
        key=f"hold_fund_editor_{ver}",
        column_config={
            "code": st.column_config.TextColumn("代码"),
            "name": st.column_config.TextColumn("名称"),
            "amount": st.column_config.NumberColumn("金额(元)", min_value=0.0, step=1000.0),
            "index": st.column_config.SelectboxColumn("跟踪指数", options=[""] + INDEX_OPTIONS),
            "enabled": st.column_config.CheckboxColumn("启用"),
            "删除": st.column_config.CheckboxColumn("删除"),
        },
    )

    def _fund_rows_from_editor(df: pd.DataFrame, *, drop_deleted: bool) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for _, r in df.iterrows():
            if drop_deleted and bool(r.get("删除")):
                continue
            code = _clean_str(r.get("code"))
            if not code and drop_deleted:
                continue
            rows.append(
                {
                    "code": code,
                    "name": _clean_str(r.get("name")),
                    "amount": _clean_float(r.get("amount")),
                    "index": _clean_str(r.get("index")),
                    "enabled": bool(r.get("enabled", True)),
                }
            )
        return rows

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        if st.button("按代码补全", width="stretch", key=f"hold_enrich_btn_{ver}"):
            raw_rows = _fund_rows_from_editor(edited, drop_deleted=False)
            enriched, n_fill = _enrich_holding_rows(raw_rows, cfg)
            st.session_state.hold_fund_rows = enriched
            st.session_state.hold_ui_ver = ver + 1
            st.session_state.hold_info_msg = f"已补全 {n_fill} 个字段" if n_fill else "未找到可补全信息（请确认代码）"
            st.rerun()
    with c2:
        if st.button("删除勾选", width="stretch", key=f"hold_fund_del_btn_{ver}"):
            kept = [r for r in _fund_rows_from_editor(edited, drop_deleted=True) if r.get("code")]
            st.session_state.hold_fund_rows = kept
            st.session_state.hold_ui_ver = ver + 1
            st.session_state.hold_info_msg = f"已删除，剩余 {len(kept)} 只基金"
            st.rerun()
    with c3:
        if st.button("同步策略建议", width="stretch", key=f"hold_sync_strategy_{ver}"):
            plan = st.session_state.get("plan")
            if plan is None:
                st.session_state.hold_info_msg = "请先到「智能仓位」生成方案，再回来同步"
                st.rerun()
            else:
                existing = _fund_rows_from_editor(edited, drop_deleted=True)
                rows = apply_strategy_to_holdings(
                    total_assets=float(getattr(plan, "total_assets", None) or total_assets),
                    sleeves=plan.sleeves,
                    existing=existing,
                )
                watch = list(st.session_state.get("hold_watch_multiselect") or [])
                for s in plan.sleeves:
                    if s.index and s.index not in watch:
                        watch.append(s.index)
                st.session_state.hold_watch_multiselect = watch
                st.session_state.hold_fund_rows = rows
                st.session_state[f"hold_total_assets_{ver + 1}"] = float(
                    getattr(plan, "total_assets", None) or total_assets
                )
                st.session_state.hold_total_assets_val = float(
                    getattr(plan, "total_assets", None) or total_assets
                )
                st.session_state.hold_ui_ver = ver + 1
                st.session_state.hold_info_msg = (
                    f"已按策略写入 {sum(1 for s in plan.sleeves if s.fund_code)} 只推荐基金，请确认后保存"
                )
                st.rerun()
    with c4:
        if st.button("保存", type="primary", width="stretch", key=f"hold_save_btn_{ver}"):
            raw_rows = _fund_rows_from_editor(edited, drop_deleted=True)
            rows, _ = _enrich_holding_rows(raw_rows, cfg)
            watch_edited = list(st.session_state.get("hold_watch_multiselect") or [])
            for r in rows:
                idx = _clean_str(r.get("index"))
                if idx and idx not in watch_edited:
                    watch_edited.append(idx)
            cfg["portfolio"] = {
                **{k: v for k, v in pf.items() if k != "index_plans"},
                "total_assets": float(total_assets),
                "holdings": rows,
            }
            cfg["portfolio"].pop("index_plans", None)
            cfg.setdefault("valuation", {})["watch_indexes"] = watch_edited
            save_config(cfg)
            st.session_state.cfg = load_config()
            st.session_state.pop("dash_snap", None)
            st.session_state.pop("_hold_cfg_stamp", None)
            st.session_state.hold_save_ok = True
            st.rerun()
    with c5:
        if st.button("重载配置", width="stretch", key=f"hold_reload_btn_{ver}"):
            st.session_state.cfg = load_config()
            st.session_state.pop("_hold_cfg_stamp", None)
            st.rerun()
    with c6:
        if st.button("清空缓存", width="stretch", key=f"hold_cache_btn_{ver}"):
            n = CacheStore(cache_dir(cfg) / "jijin_cache.db").clear()
            for k in list(st.session_state.keys()):
                if (
                    k.startswith("dash")
                    or k.startswith("screen")
                    or k.startswith("smart")
                    or k.startswith("exp_")
                    or k.startswith("opp_")
                    or k.startswith("score")
                    or k.startswith("trend")
                ):
                    st.session_state.pop(k, None)
            st.success(f"清除 {n} 条")



