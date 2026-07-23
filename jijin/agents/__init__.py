from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable

ProgressCb = Callable[[int, int, str], None]

from jijin.agents.coach import Explanation, explain_action, explain_score
from jijin.alert.position import PositionAdvice, generate_alerts
from jijin.concurrency import configured_workers
from jijin.config import load_config
from jijin.engine.scoring import ScoreBreakdown, compute_ai_score, score_indexes
from jijin.engine.trend import TrendResult, analyze_trend, analyze_trend_horizons
from jijin.engine.macro import MacroSnapshot, evaluate_macro
from jijin.portfolio.holdings import exposure_by_index, load_holdings, portfolio_total
from jijin.engine.calibrate import CalibrationResult, calibrate_trend_strategy
from jijin.screener.opportunity import IndexOpportunity, scan_index_opportunities
from jijin.strategy.generator import StrategyPlan, generate_strategy


@dataclass
class DashboardSnapshot:
    market_temperature: float | None
    market_label: str
    ai_scores: list[ScoreBreakdown]
    avg_ai_score: float | None
    advices: list[PositionAdvice]
    opportunities: list[IndexOpportunity]
    holdings_exposure: dict[str, dict[str, float]]
    total_assets: float
    explanations: dict[str, Explanation] = field(default_factory=dict)
    macro: MacroSnapshot | None = None
    opportunity_horizon: str = "未来1个月"


def valuation_agent(index: str, cfg: dict[str, Any] | None = None, force: bool = False):
    from jijin.data.valuation import fetch_index_valuation

    return fetch_index_valuation(index, cfg=cfg or load_config(), force=force)


def trend_agent(
    index: str,
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    horizon: str | None = None,
) -> TrendResult:
    return analyze_trend(index, cfg=cfg or load_config(), force=force, horizon=horizon)


def calibrate_agent(
    cfg: dict[str, Any] | None = None,
    *,
    force: bool = False,
    write_back: bool = False,
    years: float | None = None,
) -> CalibrationResult:
    """近 N 年 Walk-Forward 自动生成趋势策略参数。"""
    kwargs: dict[str, Any] = {
        "cfg": cfg or load_config(),
        "force": force,
        "write_back": write_back,
    }
    if years is not None:
        kwargs["years"] = years
    return calibrate_trend_strategy(**kwargs)


def trend_horizons_agent(
    index: str,
    cfg: dict[str, Any] | None = None,
    force: bool = False,
) -> list[TrendResult]:
    return analyze_trend_horizons(index, cfg=cfg or load_config(), force=force)


def score_agent(index: str, cfg: dict[str, Any] | None = None, force: bool = False) -> ScoreBreakdown:
    return compute_ai_score(index, cfg=cfg or load_config(), force=force)


def macro_agent(cfg: dict[str, Any] | None = None, force: bool = False) -> MacroSnapshot:
    return evaluate_macro(cfg=cfg or load_config(), force=force)


def portfolio_agent(
    *,
    risk: str = "均衡",
    template: str = "valuation_dynamic",
    monthly_dca: float = 3000.0,
    cfg: dict[str, Any] | None = None,
) -> StrategyPlan:
    return generate_strategy(
        risk=risk,
        template=template,
        monthly_dca=monthly_dca,
        cfg=cfg or load_config(),
        pick_funds=True,
    )


def coach_agent(score: ScoreBreakdown, trend: TrendResult | None = None) -> Explanation:
    return explain_score(score, trend)


def opportunity_agent(
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    top_n: int | None = None,
    on_progress: ProgressCb | None = None,
) -> list[IndexOpportunity]:
    return scan_index_opportunities(
        cfg=cfg or load_config(),
        force=force,
        top_n=top_n,
        on_progress=on_progress,
    )


def _safe_call(fn, default, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def build_dashboard(
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    on_progress: ProgressCb | None = None,
    opportunities: list[IndexOpportunity] | None = None,
) -> DashboardSnapshot:
    cfg = cfg or load_config()

    def report(done: int, total: int, msg: str = "") -> None:
        if on_progress is not None:
            on_progress(done, total, msg)

    report(0, 100, "读取持仓")
    indexes = list(cfg.get("valuation", {}).get("watch_indexes") or ["沪深300", "中证500"])
    holdings = load_holdings(cfg)
    total = portfolio_total(cfg, holdings)
    exposure = exposure_by_index(holdings, total)

    # 宏观 / 评分 / 仓位并行；指数扫描放主线程以便刷新进度条
    report(5, 100, "并行加载宏观 / 评分 / 仓位")
    workers = configured_workers(cfg, 3)
    import time

    from jijin.utils.timeout import index_timeout_sec

    parallel_timeout = min(45.0, max(25.0, index_timeout_sec(cfg, 20) * max(len(indexes), 1) / 3 + 15))
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dashboard")
    try:
        futs = {
            executor.submit(_safe_call, evaluate_macro, None, cfg, force): "宏观环境",
            executor.submit(_safe_call, score_indexes, [], indexes, cfg, force): "观察池评分",
            executor.submit(_safe_call, generate_alerts, [], cfg, force): "仓位建议",
        }
        macro = None
        scores: list = []
        advices: list = []
        finished = 0
        pending = set(futs)
        deadline = time.monotonic() + parallel_timeout
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                for fut in list(pending):
                    fut.cancel()
                report(5 + (finished + 1) * 8, 100, "并行加载超时，已跳过未完成项")
                break
            done_set, pending = wait(
                pending,
                timeout=min(2.0, remaining),
                return_when=FIRST_COMPLETED,
            )
            if not done_set:
                report(5 + finished * 8, 100, f"并行加载中… 剩余 {len(pending)} 项")
                continue
            for fut in done_set:
                label = futs[fut]
                finished += 1
                try:
                    result = fut.result(timeout=0)
                except Exception:
                    result = None
                if label == "宏观环境":
                    macro = result
                elif label == "观察池评分":
                    scores = result or []
                else:
                    advices = result or []
                report(5 + finished * 8, 100, f"已完成 {label}")
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    if opportunities is None:
        report(30, 100, "扫描市场指数机会")

        def _scan_progress(done: int, total_n: int, name: str) -> None:
            frac = done / max(int(total_n), 1)
            report(30 + int(60 * frac), 100, f"扫描 {done}/{total_n} · {name}")

        opportunities = scan_index_opportunities(
            cfg, force=force, top_n=10, on_progress=_scan_progress
        )
    else:
        report(90, 100, "复用已有机会列表")

    report(92, 100, "汇总看板")
    pe_list = [
        s.components.get("pe_percentile")
        for s in scores
        if s.components.get("pe_percentile") is not None
    ]
    temp = float(sum(pe_list) / len(pe_list)) if pe_list else None
    if temp is None:
        label = "未知"
    elif temp < 30:
        label = "偏冷·低估区"
    elif temp < 50:
        label = "温和"
    elif temp < 70:
        label = "偏暖"
    else:
        label = "偏热·高估区"
    if macro is not None:
        label = f"{label} · {macro.label}"

    opportunity_horizon = (
        opportunities[0].horizon_label if opportunities else "未来1个月"
    )

    # Dashboard only needs explanations for actionable rebalance items.
    explanations: dict[str, Explanation] = {}
    score_map = {s.index: s.total for s in scores}
    for a in advices:
        if a.action in {"增持", "减持"}:
            explanations[f"action:{a.index}"] = explain_action(
                a.action,
                a.index,
                {
                    "current_pct": a.current_pct,
                    "target_pct": a.target_pct,
                    "valuation_label": a.label,
                    "percentile": a.percentile,
                    "ai_score": score_map.get(a.index),
                },
            )

    avg_ai = float(sum(s.total for s in scores) / len(scores)) if scores else None
    report(100, 100, "完成")
    return DashboardSnapshot(
        market_temperature=None if temp is None else round(temp, 1),
        market_label=label,
        ai_scores=scores,
        avg_ai_score=None if avg_ai is None else round(avg_ai, 1),
        advices=advices,
        opportunities=opportunities,
        holdings_exposure=exposure,
        total_assets=total,
        explanations=explanations,
        macro=macro,
        opportunity_horizon=opportunity_horizon,
    )
