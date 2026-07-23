from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from jijin.concurrency import configured_workers
from jijin.data.valuation import IndexValuation, fetch_index_valuation
from jijin.engine.macro import MacroSnapshot, evaluate_macro
from jijin.engine.settings import (
    DEFAULT_SCORING_SETTINGS,
    get_macro_settings,
    get_scoring_settings,
)
from jijin.engine.trend import TrendResult, analyze_trend


@dataclass
class ScoreBreakdown:
    index: str
    total: float
    valuation: float
    trend: float
    capital: float
    earnings: float
    risk: float
    sentiment: float
    macro: float
    policy: float
    label: str  # 机会 / 中性 / 谨慎
    components: dict[str, Any] = field(default_factory=dict)


# Backward-compatible default constant. Runtime scoring uses config.yaml.
WEIGHTS = DEFAULT_SCORING_SETTINGS["weights"]


def _valuation_score(pe_pct: float | None, pb_pct: float | None) -> float:
    """低估高分（更适合长期买入视角）。"""
    scores = []
    if pe_pct is not None:
        scores.append(float(np.clip(100 - pe_pct, 0, 100)))
    if pb_pct is not None:
        scores.append(float(np.clip(100 - pb_pct, 0, 100)))
    if not scores:
        return 50.0
    return float(np.mean(scores))


def _earnings_score(pe: float | None, pe_pct: float | None) -> float:
    """盈利维度：PE 合理且不过高给分；无数据中性。"""
    if pe is None:
        return 50.0
    if 8 <= pe <= 25:
        base = 75
    elif pe < 8:
        base = 60
    elif pe <= 40:
        base = 45
    else:
        base = 25
    if pe_pct is not None:
        base -= max(0, (pe_pct - 60) * 0.4)
    return float(np.clip(base, 5, 95))


def _risk_score(trend: TrendResult) -> float:
    """风险越低分越高。"""
    vol = trend.volatility or 18
    if vol <= 15:
        v = 85
    elif vol <= 22:
        v = 70
    elif vol <= 30:
        v = 45
    else:
        v = 25
    if trend.risk_level == "高":
        v -= 15
    elif trend.risk_level == "低":
        v += 5
    return float(np.clip(v, 5, 95))


def _capital_score(trend: TrendResult) -> float:
    """资金面：量能 + 动量近似。"""
    mapping = {
        "放量上涨": 80,
        "量能平稳": 55,
        "缩量": 45,
        "放量下跌": 25,
        "平稳": 50,
        "未知": 50,
    }
    base = mapping.get(trend.volume_trend, 50)
    if trend.momentum_20d is not None:
        base += float(np.clip(trend.momentum_20d, -15, 15))
    return float(np.clip(base, 5, 95))


def _sentiment_score(trend: TrendResult) -> float:
    """情绪：RSI + 短期动量。"""
    rsi = trend.rsi if trend.rsi is not None else 50
    if 40 <= rsi <= 60:
        s = 70
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        s = 55
    elif rsi < 30:
        s = 65
    else:
        s = 35
    if trend.momentum_20d is not None:
        s += float(np.clip(trend.momentum_20d * 0.5, -10, 10))
    return float(np.clip(s, 5, 95))


def _label(total: float, labels: dict[str, float]) -> str:
    if total >= labels["opportunity_min"]:
        return "机会"
    if total >= labels["neutral_min"]:
        return "中性"
    return "谨慎"


def compute_ai_score(
    index: str,
    valuation: IndexValuation | None = None,
    trend: TrendResult | None = None,
    macro: MacroSnapshot | None = None,
    cfg: dict[str, Any] | None = None,
    force: bool = False,
) -> ScoreBreakdown:
    from jijin.config import load_config

    cfg = cfg or load_config()
    scoring_settings = get_scoring_settings(cfg)
    weights = scoring_settings["weights"]
    labels = scoring_settings["labels"]
    macro_enabled = get_macro_settings(cfg)["enabled"]

    if valuation is None:
        try:
            valuation = fetch_index_valuation(index, cfg=cfg, force=force)
        except Exception:
            valuation = None
    if trend is None:
        try:
            trend = analyze_trend(index, cfg=cfg, force=force)
        except Exception:
            trend = TrendResult(
                index=index,
                score=50,
                risk_level="中",
                probability_up=0.5,
                ma_signal="未知",
                macd_signal="未知",
                rsi=None,
                volatility=None,
                momentum_20d=None,
                volume_trend="未知",
                strength=0,
            )
    if macro is None and macro_enabled:
        try:
            macro = evaluate_macro(cfg=cfg, force=force)
        except Exception:
            macro = None

    v_score = _valuation_score(
        None if valuation is None else valuation.pe_percentile,
        None if valuation is None else valuation.pb_percentile,
    )
    t_score = float(trend.score)
    c_score = _capital_score(trend)
    e_score = _earnings_score(
        None if valuation is None else valuation.pe,
        None if valuation is None else valuation.pe_percentile,
    )
    r_score = _risk_score(trend)
    s_score = _sentiment_score(trend)
    m_score = 50.0 if macro is None else float(macro.macro_score)
    p_score = 50.0 if macro is None else float(macro.policy_score)

    # 关闭宏观模块时，把宏观/政策权重并入估值与趋势，避免静默稀释
    active_weights = dict(weights)
    if not macro_enabled:
        spill = active_weights.get("macro", 0.0) + active_weights.get("policy", 0.0)
        active_weights["macro"] = 0.0
        active_weights["policy"] = 0.0
        active_weights["valuation"] = active_weights.get("valuation", 0.0) + spill * 0.6
        active_weights["trend"] = active_weights.get("trend", 0.0) + spill * 0.4
        total_w = sum(active_weights.values()) or 1.0
        active_weights = {k: v / total_w for k, v in active_weights.items()}

    total = (
        active_weights["valuation"] * v_score
        + active_weights["trend"] * t_score
        + active_weights["capital"] * c_score
        + active_weights["earnings"] * e_score
        + active_weights["risk"] * r_score
        + active_weights["sentiment"] * s_score
        + active_weights["macro"] * m_score
        + active_weights["policy"] * p_score
    )
    total = float(np.clip(total, 0, 100))

    return ScoreBreakdown(
        index=index,
        total=round(total, 1),
        valuation=round(v_score, 1),
        trend=round(t_score, 1),
        capital=round(c_score, 1),
        earnings=round(e_score, 1),
        risk=round(r_score, 1),
        sentiment=round(s_score, 1),
        macro=round(m_score, 1),
        policy=round(p_score, 1),
        label=_label(total, labels),
        components={
            "weights": active_weights,
            "label_thresholds": labels,
            "pe": None if valuation is None else valuation.pe,
            "pe_percentile": None if valuation is None else valuation.pe_percentile,
            "pb_percentile": None if valuation is None else valuation.pb_percentile,
            "trend_risk": trend.risk_level,
            "probability_up": trend.probability_up,
            "macro_enabled": macro_enabled,
            "macro_label": None if macro is None else macro.label,
            "policy_stance": None if macro is None else macro.stance,
            "pmi": None if macro is None else macro.pmi,
            "cpi": None if macro is None else macro.cpi,
            "m2_yoy": None if macro is None else macro.m2_yoy,
            "lpr_1y": None if macro is None else macro.lpr_1y,
            "lpr_delta": None if macro is None else macro.lpr_delta,
        },
    )


def score_indexes(
    indexes: list[str],
    cfg: dict[str, Any] | None = None,
    force: bool = False,
) -> list[ScoreBreakdown]:
    from jijin.config import load_config

    cfg = cfg or load_config()
    macro_snap = None
    if get_macro_settings(cfg)["enabled"]:
        try:
            macro_snap = evaluate_macro(cfg=cfg, force=force)
        except Exception:
            macro_snap = None
    if not indexes:
        return []

    workers = configured_workers(cfg, len(indexes))
    by_index: dict[str, ScoreBreakdown] = {}
    from jijin.utils.timeout import index_timeout_sec

    per_index = index_timeout_sec(cfg, 20)
    executor = ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="index-score",
    )
    try:
        futures = {
            executor.submit(
                compute_ai_score,
                index,
                macro=macro_snap,
                cfg=cfg,
                force=force,
            ): index
            for index in indexes
        }
        for future in as_completed(futures, timeout=per_index * (len(indexes) / max(workers, 1) + 1)):
            index = futures[future]
            try:
                by_index[index] = future.result(timeout=0)
            except Exception:
                continue
    except TimeoutError:
        pass
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    # Keep caller-supplied ordering stable despite concurrent completion.
    return [by_index[index] for index in indexes if index in by_index]
