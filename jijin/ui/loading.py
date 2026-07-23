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

def loading_progress(title: str) -> Iterator[Callable[[int, int, str], None]]:
    """原生进度条（策略校准等仍在主线程跑的场景）。"""
    slot = st.empty()
    last = {"done": 0, "total": 1}

    def update(done: int, total: int, msg: str = "", *, force: bool = False) -> None:
        _ = force
        total_n = max(int(total), 1)
        cur = max(0, min(int(done), total_n))
        last["done"] = cur
        last["total"] = total_n
        pct = cur / total_n
        label = f"{title} · {cur}/{total_n}"
        if msg:
            label = f"{label} · {msg}"
        with slot.container():
            try:
                st.progress(pct, text=label)
            except TypeError:
                st.progress(pct)

    update(0, 1, "准备中")
    try:
        yield update
    finally:
        try:
            update(last["total"], last["total"], "完成")
        except Exception:  # noqa: BLE001
            pass
        slot.empty()


def _compute_score_payload(
    cfg: dict[str, Any],
    pick: list[str],
    force: bool,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """计算评分/多周期趋势（多线程并行），返回待写入 session 的数据。"""
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    from jijin.concurrency import configured_workers
    from jijin.engine.macro import evaluate_macro
    from jijin.engine.settings import get_macro_settings
    from jijin.utils.timeout import call_with_timeout

    default_horizon = get_trend_settings(cfg).get("default_horizon", "1m")
    rows: list[dict[str, Any]] = []
    trends: dict[str, Any] = {}
    multi: dict[str, Any] = {}
    explanations: dict[str, Any] = {}
    warnings: list[str] = []
    total_n = max(len(pick), 1)
    per_index_timeout = float((cfg.get("cache") or {}).get("score_index_timeout_sec") or 20)
    workers = configured_workers(cfg, len(pick))

    # 宏观只算一次，避免每个指数重复拉 PMI/CPI
    macro_snap = None
    if get_macro_settings(cfg).get("enabled"):
        try:
            macro_snap = call_with_timeout(lambda: evaluate_macro(cfg=cfg, force=force), 25)
        except Exception:  # noqa: BLE001
            macro_snap = None

    def _one(name: str) -> tuple[str, Any, list[Any], Any, Any]:
        # 先多周期（内部只拉一次日线），再评分复用趋势，少一次行情请求
        from jijin.engine.scoring import compute_ai_score

        horizons = trend_horizons_agent(name, cfg=cfg, force=force)
        tr = next(
            (h for h in horizons if h.horizon == default_horizon),
            next((h for h in horizons if h.horizon == "1m"), horizons[0]),
        )
        sc = compute_ai_score(name, trend=tr, macro=macro_snap, cfg=cfg, force=force)
        explanation = coach_agent(sc, tr)
        return name, sc, horizons, tr, explanation

    def report(done: int, total: int, msg: str = "") -> None:
        if on_progress is not None:
            on_progress(done, total, msg)

    report(0, total_n, f"并行计算 · {workers} 线程")

    def _row_from(sc: Any, tr: Any) -> dict[str, Any]:
        st_dir = (tr.details or {}).get("supertrend_dir")
        st_label = "—"
        if st_dir is not None:
            st_label = "多" if int(st_dir) >= 1 else "空"
        mtf = (tr.details or {}).get("mtf_align")
        mtf_txt = "—"
        if isinstance(mtf, dict) and mtf.get("agree") is not None:
            mtf_txt = f"一致{mtf.get('agree', 0)}/冲突{mtf.get('conflict', 0)}"
        return {
            "指数": sc.index,
            "AI分": sc.total,
            "标签": sc.label,
            "估值": sc.valuation,
            "趋势": sc.trend,
            "资金": sc.capital,
            "盈利": sc.earnings,
            "风险分": sc.risk,
            "情绪": sc.sentiment,
            "宏观": sc.macro,
            "政策": sc.policy,
            "参考展望": tr.horizon_label,
            "方向": tr.bias,
            "趋势分": tr.score,
            "体制": (tr.details or {}).get("regime") or "—",
            "Supertrend": st_label,
            "强度": tr.strength,
            "MTF": mtf_txt,
            "趋势风险": tr.risk_level,
            "偏多概率": tr.probability_up,
            "波动带宽%": tr.move_band_pct,
            "MA": tr.ma_signal,
            "MACD": tr.macd_signal,
            "RSI": tr.rsi,
            "波动%": tr.volatility,
            "动量%": tr.momentum_20d,
            "量能": tr.volume_trend,
        }

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="score-par")
    try:
        futures = {
            executor.submit(call_with_timeout, _one, per_index_timeout, name): name
            for name in pick
        }
        pending = set(futures)
        done = 0
        import time

        overall = max(per_index_timeout + 5, per_index_timeout * (len(pick) / max(workers, 1) + 1))
        deadline = time.monotonic() + overall
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            finished, pending = wait(
                pending, timeout=min(1.0, remaining), return_when=FIRST_COMPLETED
            )
            if not finished:
                report(done, total_n, f"并行中… 剩余 {len(pending)}")
                continue
            for fut in finished:
                name = futures[fut]
                done += 1
                try:
                    _n, sc, horizons, tr, explanation = fut.result(timeout=0)
                    multi[name] = horizons
                    trends[name] = tr
                    explanations[f"exp_{name}"] = explanation
                    rows.append(_row_from(sc, tr))
                    report(done, total_n, name)
                except TimeoutError:
                    warnings.append(f"{name}: 数据请求超时，已跳过")
                    report(done, total_n, f"{name} · 超时")
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{name}: {exc}")
                    report(done, total_n, name)
        for fut in pending:
            name = futures[fut]
            fut.cancel()
            warnings.append(f"{name}: 批次超时")
            done += 1
            report(min(done, total_n), total_n, f"{name} · 超时")
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    # 保持用户选择顺序
    order = {n: i for i, n in enumerate(pick)}
    rows.sort(key=lambda r: order.get(str(r.get("指数")), 10**9))

    failed = [n for n in pick if n not in multi]
    out: dict[str, Any] = {
        "score_table": pd.DataFrame(rows),
        "trend_map": trends,
        "trend_multi": multi,
        "score_cache_key": score_cache_key(list(pick), str(default_horizon)),
        "score_fetched_at": pd.Timestamp.now().strftime("%H:%M:%S"),
        "score_load_warnings": (
            [f"{n}: 请求失败或超时" for n in failed] if failed else warnings
        ),
        "explanations": explanations,
        "_score_load_failed": bool(pick and not multi),
    }
    return out


def _refresh_score_cache(cfg: dict[str, Any], pick: list[str], force: bool) -> None:
    """主线程兼容包装（校准等）；优先走后台加载。"""
    with loading_progress("计算评分与多周期趋势") as progress:
        payload = _compute_score_payload(cfg, pick, force, on_progress=progress)
    _apply_load_payload(payload)


def _apply_load_payload(payload: dict[str, Any]) -> None:
    """把后台任务结果写入 session_state。"""
    explanations = payload.pop("explanations", None)
    score_failed = payload.pop("_score_load_failed", None)
    for key, value in list(payload.items()):
        if key in {
            "_dash_load_failed",
            "_opp_load_failed",
            "_alert_load_failed",
            "_score_load_failed",
        }:
            if value:
                st.session_state[key] = True
            else:
                st.session_state.pop(key, None)
            continue
        st.session_state[key] = value
    if isinstance(explanations, dict):
        for key, value in explanations.items():
            st.session_state[key] = value
    if score_failed:
        st.session_state["_score_load_failed"] = True
    elif score_failed is False:
        st.session_state.pop("_score_load_failed", None)


def _build_load_fn(
    cfg: dict[str, Any],
    page: str,
    job: dict[str, Any] | None,
) -> tuple[str, Callable[[Callable[[int, int, str], None]], dict[str, Any]]]:
    """构造后台加载函数：只返回 session 更新，不触碰 Streamlit。"""
    if job and isinstance(job, dict):
        kind = str(job.get("kind") or "")
        force = bool(job.get("force"))
        if kind == "dashboard":

            def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
                snap = build_dashboard(cfg, force=force, on_progress=progress)
                return {"dash_snap": snap, "_dash_load_failed": False}

            return "dashboard", _fn
        if kind == "opportunity":
            group = str(job.get("group") or "全部")
            run_cfg = dict(cfg)
            run_cfg["opportunity"] = {
                **dict(cfg.get("opportunity") or {}),
                "universe_group": None if group == "全部" else group,
                "top_n": int(job.get("top_n") or 15),
            }

            def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
                items = opportunity_agent(
                    cfg=run_cfg,
                    force=force,
                    top_n=run_cfg["opportunity"]["top_n"],
                    on_progress=progress,
                )
                return {
                    "opp_list": items,
                    "opp_cache_key": job.get("cache_key"),
                    "opp_fetched_at": pd.Timestamp.now().strftime("%H:%M:%S"),
                    "_opp_load_failed": False,
                }

            return "opportunity", _fn
        if kind == "score":
            pick = list(job.get("pick") or [])

            def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
                return _compute_score_payload(cfg, pick, force, on_progress=progress)

            return "score", _fn
        if kind == "alerts":

            def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
                alerts = generate_smart_alerts(cfg, force=force, on_progress=progress)
                return {
                    "smart_alerts": alerts,
                    "alert_fetched_at": pd.Timestamp.now().strftime("%H:%M:%S"),
                    "_alert_load_failed": False,
                }

            return "alerts", _fn

    # 换页预取
    if page == "看板":

        def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
            snap = build_dashboard(cfg, force=False, on_progress=progress)
            return {"dash_snap": snap}

        return "dashboard", _fn
    if page == "重点机会":
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
        run_cfg = dict(cfg)
        run_cfg["opportunity"] = {
            **dict(cfg.get("opportunity") or {}),
            "universe_group": None if group == "全部" else group,
            "top_n": int((cfg.get("opportunity") or {}).get("top_n") or 15),
        }

        def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
            items = opportunity_agent(
                cfg=run_cfg,
                force=False,
                top_n=run_cfg["opportunity"]["top_n"],
                on_progress=progress,
            )
            return {
                "opp_list": items,
                "opp_cache_key": cache_key,
                "opp_fetched_at": pd.Timestamp.now().strftime("%H:%M:%S"),
            }

        return "opportunity", _fn
    if page == "评分趋势":
        indexes = list(cfg.get("valuation", {}).get("watch_indexes") or ["沪深300", "中证500"])
        pick = list(st.session_state.get("score_pick") or indexes) or indexes

        def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
            return _compute_score_payload(cfg, pick, False, on_progress=progress)

        return "score", _fn
    if page == "智能提醒":

        def _fn(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
            alerts = generate_smart_alerts(cfg, force=False, on_progress=progress)
            return {
                "smart_alerts": alerts,
                "alert_fetched_at": pd.Timestamp.now().strftime("%H:%M:%S"),
            }

        return "alerts", _fn

    def _noop(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
        _ = progress
        return {}

    return "noop", _noop


def _render_loading_panel(page: str, done: int, total: int, message: str, elapsed: float) -> None:
    """主线程可反复重绘的加载面板（不依赖 components.html）。"""
    total_n = max(int(total), 1)
    cur = max(0, min(int(done), total_n))
    pct = cur / total_n
    label = f"{cur}/{total_n}"
    if message:
        label = f"{label} · {message}"
    st.markdown(
        f"""
<div class="load-panel">
  <p class="load-kicker">AI INDEX</p>
  <h2 class="load-title">正在打开「{escape(page)}」</h2>
  <p class="load-sub">数据在后台加载，界面保持响应 · 已用时 {elapsed:.0f}s</p>
</div>
        """,
        unsafe_allow_html=True,
    )
    try:
        st.progress(pct, text=label)
    except TypeError:
        st.progress(pct)
        st.caption(label)


def _prefetch_page_data(page: str, cfg: dict[str, Any]) -> None:
    """兼容旧路径：同步预取（仅非 UI 调用时使用）。"""
    _kind, fn = _build_load_fn(cfg, page, None)
    payload = fn(lambda *_a, **_k: None)
    _apply_load_payload(payload)


