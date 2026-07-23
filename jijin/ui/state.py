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

from jijin.ui.constants import INDEX_OPTIONS

def get_cfg() -> dict[str, Any]:
    if "cfg" not in st.session_state:
        st.session_state.cfg = load_config()
    return st.session_state.cfg


def _is_blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    s = str(val).strip()
    return (not s) or s.lower() in {"nan", "none", "<na>"}


def _clean_str(val: Any) -> str:
    return "" if _is_blank(val) else str(val).strip()


def _clean_float(val: Any, default: float = 0.0) -> float:
    if _is_blank(val):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _holdings_records(pf: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in pf.get("holdings") or []:
        rows.append(
            {
                "code": _clean_str(h.get("code")),
                "name": _clean_str(h.get("name")),
                "amount": _clean_float(h.get("amount")),
                "index": _clean_str(h.get("index")),
                "enabled": bool(h.get("enabled", True)),
            }
        )
    return rows


def _sync_holdings_editor_state(cfg: dict[str, Any]) -> None:
    """从配置刷新持仓页编辑缓存（不触碰已渲染的 widget key）。"""
    pf = dict(cfg.get("portfolio") or {})
    watch = [n for n in list((cfg.get("valuation") or {}).get("watch_indexes") or []) if n in INDEX_SYMBOLS]
    records = _holdings_records(pf)
    cfg_path = str(cfg.get("_config_path") or "")
    stamp = (
        cfg_path,
        tuple(watch),
        tuple((r["code"], r["name"], r["amount"], r["index"], r["enabled"]) for r in records),
        float(pf.get("total_assets") or 0),
    )
    if st.session_state.get("_hold_cfg_stamp") == stamp:
        return
    st.session_state.hold_watch_multiselect = list(watch)
    st.session_state.hold_fund_rows = records
    st.session_state.hold_total_assets_val = float(
        pf.get("total_assets")
        or sum(float(h.get("amount") or 0) for h in (pf.get("holdings") or []))
    )
    st.session_state.hold_ui_ver = int(st.session_state.get("hold_ui_ver") or 0) + 1
    st.session_state._hold_cfg_stamp = stamp


def _enrich_holding_rows(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """按基金代码补全名称与跟踪指数。返回 (新行, 补全条数)。"""
    out: list[dict[str, Any]] = []
    filled = 0
    for raw in rows:
        code = re.sub(r"\D", "", _clean_str(raw.get("code")))
        if not code:
            continue
        code = code.zfill(6)
        name = _clean_str(raw.get("name"))
        index = _clean_str(raw.get("index"))
        need_name = not name
        need_index = not index or index not in INDEX_SYMBOLS
        if need_name or need_index:
            info = lookup_fund_by_code(code, cfg)
            if info:
                if need_name and info.get("name"):
                    name = str(info["name"])
                    filled += 1
                if need_index and info.get("index") and info["index"] in INDEX_SYMBOLS:
                    index = str(info["index"])
                    filled += 1
        out.append(
            {
                "code": code,
                "name": name,
                "amount": _clean_float(raw.get("amount")),
                "index": index if index in INDEX_SYMBOLS else "",
                "enabled": bool(raw.get("enabled", True)),
            }
        )
    return out, filled


def _invalidate_analysis_state() -> None:
    for key in list(st.session_state.keys()):
        if key in {
            "dash_snap",
            "dash_cache_key",
            "opp_list",
            "opp_cache_key",
            "opp_fetched_at",
            "score_table",
            "trend_map",
            "trend_multi",
            "score_cache_key",
            "score_fetched_at",
            "smart_alerts",
            "alert_fetched_at",
            "cal_result",
        } or str(key).startswith("exp_"):
            st.session_state.pop(key, None)


def _purge_ephemeral_ui_state() -> None:
    """切换侧边栏页面时清理易串页的控件状态，避免上一页 UI/数值残留。"""
    for k in ("hold_save_ok", "hold_info_msg"):
        st.session_state.pop(k, None)
    prefixes = (
        "hold_total_assets_",
        "hold_fund_editor_",
        "hold_enrich_btn_",
        "hold_fund_del_btn_",
        "hold_sync_strategy_",
        "hold_save_btn_",
        "hold_reload_btn_",
        "hold_cache_btn_",
        "tw_",
        "sw_",
        "mw_",
        "FormSubmitter:",
        "pos_form",
    )
    sticky_widget_keys = {
        "hold_watch_multiselect",
        "dash_force",
        "opp_force",
        "opp_group",
        "score_force",
        "alert_force",
    }
    for k in list(st.session_state.keys()):
        sk = str(k)
        if sk in sticky_widget_keys or any(sk.startswith(p) for p in prefixes):
            st.session_state.pop(k, None)
    st.session_state.pop("_hold_cfg_stamp", None)


