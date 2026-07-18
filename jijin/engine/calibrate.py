from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from jijin.config import load_config, save_config
from jijin.data.market import INDEX_SYMBOLS, fetch_index_daily
from jijin.engine.settings import (
    DEFAULT_TREND_SETTINGS,
    normalize_weights,
)


WEIGHT_KEYS = ("ma", "macd", "rsi", "momentum", "volume")

# 粗网格：优先稳健、避免过细搜索导致过拟合
WEIGHT_CANDIDATES: list[dict[str, float]] = [
    {"ma": 0.30, "macd": 0.25, "rsi": 0.15, "momentum": 0.15, "volume": 0.15},  # default
    {"ma": 0.40, "macd": 0.20, "rsi": 0.10, "momentum": 0.20, "volume": 0.10},  # trend-heavy
    {"ma": 0.20, "macd": 0.20, "rsi": 0.25, "momentum": 0.20, "volume": 0.15},  # short-term
    {"ma": 0.25, "macd": 0.15, "rsi": 0.15, "momentum": 0.30, "volume": 0.15},  # momentum
    {"ma": 0.20, "macd": 0.15, "rsi": 0.15, "momentum": 0.15, "volume": 0.35},  # volume
    {"ma": 0.35, "macd": 0.25, "rsi": 0.20, "momentum": 0.10, "volume": 0.10},  # classic TA
]

RSI_CANDIDATES: list[tuple[float, float]] = [
    (25.0, 75.0),
    (30.0, 70.0),
    (35.0, 65.0),
]

INDICATOR_CANDIDATES: list[dict[str, int]] = [
    {},  # keep defaults
    {"ma_short": 10, "ma_medium": 30, "ma_long": 60, "roc_length": 10},
    {"ma_short": 20, "ma_medium": 60, "ma_long": 120, "roc_length": 20},
    {"ma_short": 50, "ma_medium": 100, "ma_long": 200, "roc_length": 40},
]


@dataclass
class CalibrationMetrics:
    hit_rate: float
    ic: float
    sharpe: float
    samples: int


@dataclass
class CalibrationResult:
    accepted: bool
    reason: str
    best_trend: dict[str, Any]
    default_oos: CalibrationMetrics
    best_oos: CalibrationMetrics
    best_is: CalibrationMetrics
    indexes_used: list[str]
    lookback_days: int
    forward_days: int
    folds: int
    shrinkage: float
    details: dict[str, Any] = field(default_factory=dict)


def _annualized_sharpe(returns: pd.Series) -> float:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    if len(r) < 10 or float(r.std()) <= 1e-12:
        return 0.0
    return float(np.sqrt(252) * r.mean() / r.std())


def _spearman_ic(pred: pd.Series, actual: pd.Series) -> float:
    df = pd.DataFrame({"p": pred, "a": actual}).dropna()
    if len(df) < 20:
        return 0.0
    # 不依赖 scipy：用秩相关（平均秩处理并列）
    pr = df["p"].rank(method="average")
    ar = df["a"].rank(method="average")
    corr = pr.corr(ar, method="pearson")
    if corr is None or (isinstance(corr, float) and np.isnan(corr)):
        return 0.0
    return float(corr)


def _component_scores(
    df: pd.DataFrame,
    indicators: dict[str, Any],
    thresholds: dict[str, Any],
) -> pd.DataFrame:
    """向量化复刻趋势引擎分项分，便于历史回测。"""
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = (
        pd.to_numeric(df["volume"], errors="coerce")
        if "volume" in df.columns
        else pd.Series(np.nan, index=df.index)
    )

    ma_short_n = int(indicators["ma_short"])
    ma_medium_n = int(indicators["ma_medium"])
    macd_fast = int(indicators["macd_fast"])
    macd_slow = int(indicators["macd_slow"])
    macd_signal = int(indicators["macd_signal"])
    rsi_n = int(indicators["rsi_length"])
    roc_n = int(indicators["roc_length"])
    volume_n = int(indicators["volume_window"])
    rsi_ob = float(thresholds["rsi_overbought"])
    rsi_os = float(thresholds["rsi_oversold"])
    vol_expand = float(thresholds["volume_expand_ratio"])
    vol_contract = float(thresholds["volume_contract_ratio"])

    ma_s = ta.sma(close, length=ma_short_n)
    ma_m = ta.sma(close, length=ma_medium_n)
    macd = ta.macd(close, fast=macd_fast, slow=macd_slow, signal=macd_signal)
    rsi = ta.rsi(close, length=rsi_n)
    roc = ta.roc(close, length=roc_n)

    if macd is None or macd.empty:
        hist = pd.Series(np.nan, index=close.index)
    else:
        hist = macd[f"MACDh_{macd_fast}_{macd_slow}_{macd_signal}"]

    ma_score = pd.Series(50.0, index=close.index)
    bull = (close > ma_s) & (ma_s > ma_m)
    bear = (close < ma_s) & (ma_s < ma_m)
    above = close > ma_m
    ma_score = np.where(bull, 80.0, np.where(bear, 20.0, np.where(above, 65.0, 35.0)))

    hist_prev = hist.shift(1)
    macd_score = np.where(
        (hist > 0) & (hist > hist_prev),
        75.0,
        np.where(hist > 0, 60.0, np.where((hist < 0) & (hist < hist_prev), 25.0, 40.0)),
    )

    rsi_vals = rsi.fillna(50.0)
    rsi_score = np.where(
        rsi_vals >= rsi_ob,
        35.0,
        np.where(rsi_vals <= rsi_os, 70.0, 40.0 + (rsi_vals - 50.0) * 0.8),
    )

    mom = roc.fillna(0.0)
    mom_score = (50.0 + mom * 2.0).clip(5.0, 95.0)

    vol_ma1 = volume.rolling(volume_n).mean()
    vol_ma0 = volume.shift(volume_n).rolling(volume_n).mean()
    ratio = vol_ma1 / vol_ma0
    vol_score = np.where(
        (ratio > vol_expand) & (mom > 0),
        70.0,
        np.where(
            (ratio > vol_expand) & (mom < 0),
            30.0,
            np.where(ratio < vol_contract, 45.0, 55.0),
        ),
    )
    vol_score = np.where(ratio.isna(), 50.0, vol_score)

    out = pd.DataFrame(
        {
            "ma": ma_score,
            "macd": macd_score,
            "rsi": rsi_score,
            "momentum": mom_score,
            "volume": vol_score,
            "close": close,
        },
        index=df.index,
    )
    return out


def _score_series(components: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    w = normalize_weights(weights, DEFAULT_TREND_SETTINGS["weights"])
    score = sum(float(w[k]) * components[k] for k in WEIGHT_KEYS)
    return pd.Series(score, index=components.index).clip(0, 100)


def _evaluate_window(
    components: pd.DataFrame,
    weights: dict[str, float],
    forward_days: int,
) -> CalibrationMetrics:
    score = _score_series(components, weights)
    fwd = components["close"].shift(-forward_days) / components["close"] - 1.0
    aligned = pd.DataFrame({"score": score, "fwd": fwd}).dropna()
    if len(aligned) < 30:
        return CalibrationMetrics(hit_rate=0.5, ic=0.0, sharpe=0.0, samples=len(aligned))

    pred_up = aligned["score"] >= 55
    actual_up = aligned["fwd"] > 0
    hit = float((pred_up == actual_up).mean())
    ic = _spearman_ic(aligned["score"], aligned["fwd"])

    # 简化多空：分>=55 持有，否则空仓；收益按日均摊 forward 收益
    daily = components["close"].pct_change()
    position = (score.shift(1) >= 55).astype(float)
    strat = (position * daily).dropna()
    sharpe = _annualized_sharpe(strat)
    return CalibrationMetrics(hit_rate=hit, ic=ic, sharpe=sharpe, samples=len(aligned))


def _metrics_dict(m: CalibrationMetrics) -> dict[str, Any]:
    return {
        "hit_rate": float(m.hit_rate),
        "ic": float(m.ic),
        "sharpe": float(m.sharpe),
        "samples": int(m.samples),
    }


def _py_weights(weights: dict[str, float]) -> dict[str, float]:
    return {k: float(weights[k]) for k in WEIGHT_KEYS}


def _objective(m: CalibrationMetrics) -> float:
    """综合目标：方向命中 + IC + 风险调整收益。"""
    return float(
        0.45 * (m.hit_rate - 0.5) * 2
        + 0.35 * m.ic
        + 0.20 * np.tanh(m.sharpe / 2)
    )


def _shrink_weights(
    best: dict[str, float],
    defaults: dict[str, float],
    shrinkage: float,
) -> dict[str, float]:
    s = float(np.clip(shrinkage, 0.0, 1.0))
    mixed = {k: (1 - s) * float(best[k]) + s * float(defaults[k]) for k in WEIGHT_KEYS}
    return normalize_weights(mixed, defaults)


def _merge_indicators(base: dict[str, Any], override: dict[str, int]) -> dict[str, Any]:
    out = deepcopy(base)
    out.update(override or {})
    # keep SMA order
    if not (out["ma_short"] < out["ma_medium"] < out["ma_long"]):
        return deepcopy(base)
    if out["macd_fast"] >= out["macd_slow"]:
        return deepcopy(base)
    return out


def load_calibration_frames(
    indexes: list[str],
    cfg: dict[str, Any],
    *,
    years: float = 5.0,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    limit = int(max(400, years * 252 + 40))
    frames: dict[str, pd.DataFrame] = {}
    for name in indexes:
        try:
            df = fetch_index_daily(name, cfg=cfg, force=force, limit=limit)
            if df is None or len(df) < 300:
                continue
            work = df.copy()
            if "date" in work.columns:
                work = work.sort_values("date")
            frames[name] = work.reset_index(drop=True)
        except Exception:
            continue
    return frames


def calibrate_trend_strategy(
    cfg: dict[str, Any] | None = None,
    *,
    indexes: list[str] | None = None,
    years: float = 5.0,
    forward_days: int = 21,
    train_days: int = 504,
    test_days: int = 63,
    step_days: int = 63,
    shrinkage: float = 0.35,
    force: bool = False,
    write_back: bool = False,
) -> CalibrationResult:
    """用近 N 年指数日线做 Walk-Forward，自动生成趋势权重/阈值。

    方法取舍（相对更主流、更稳）：
    - Walk-Forward 样本外评估，降低全样本过拟合；
    - 目标综合方向命中率、Spearman IC、简化多空 Sharpe；
    - 最优参数向默认值收缩（shrinkage）；
    - 仅当 OOS 目标显著优于默认才写回。
    """
    cfg = cfg or load_config()
    cal_cfg = dict(cfg.get("calibration") or {})
    years = float(cal_cfg.get("years", years))
    forward_days = int(cal_cfg.get("forward_days", forward_days))
    train_days = int(cal_cfg.get("train_days", train_days))
    test_days = int(cal_cfg.get("test_days", test_days))
    step_days = int(cal_cfg.get("step_days", step_days))
    shrinkage = float(cal_cfg.get("shrinkage", shrinkage))

    universe = list(
        indexes
        or cfg.get("valuation", {}).get("watch_indexes")
        or list(INDEX_SYMBOLS.keys())[:6]
    )
    # 校准宇宙：观察指数优先，不足时补全市场指数
    if len(universe) < 3:
        for name in INDEX_SYMBOLS:
            if name not in universe:
                universe.append(name)
            if len(universe) >= 6:
                break

    frames = load_calibration_frames(universe, cfg, years=years, force=force)
    if len(frames) < 2:
        return CalibrationResult(
            accepted=False,
            reason="可用指数历史不足（至少需要 2 个指数、约 300 个交易日）",
            best_trend=deepcopy(DEFAULT_TREND_SETTINGS),
            default_oos=CalibrationMetrics(0.5, 0.0, 0.0, 0),
            best_oos=CalibrationMetrics(0.5, 0.0, 0.0, 0),
            best_is=CalibrationMetrics(0.5, 0.0, 0.0, 0),
            indexes_used=[],
            lookback_days=0,
            forward_days=forward_days,
            folds=0,
            shrinkage=shrinkage,
        )

    base_indicators = deepcopy(DEFAULT_TREND_SETTINGS["indicators"])
    base_thresholds = deepcopy(DEFAULT_TREND_SETTINGS["thresholds"])
    default_weights = deepcopy(DEFAULT_TREND_SETTINGS["weights"])

    # 预计算各指标方案下的分项序列
    component_cache: dict[str, dict[str, pd.DataFrame]] = {}
    for ind_key, ind_override in enumerate(INDICATOR_CANDIDATES):
        indicators = _merge_indicators(base_indicators, ind_override)
        for rsi_os, rsi_ob in RSI_CANDIDATES:
            thresholds = {
                **base_thresholds,
                "rsi_oversold": rsi_os,
                "rsi_overbought": rsi_ob,
            }
            key = f"i{ind_key}|rsi{rsi_os:.0f}-{rsi_ob:.0f}"
            component_cache[key] = {}
            for name, df in frames.items():
                component_cache[key][name] = _component_scores(df, indicators, thresholds)

    def eval_candidate(
        cache_key: str,
        weights: dict[str, float],
    ) -> tuple[CalibrationMetrics, CalibrationMetrics, int]:
        is_hits, is_ics, is_sharpes = [], [], []
        oos_hits, oos_ics, oos_sharpes = [], [], []
        folds = 0
        min_len = min(len(df) for df in frames.values())
        start = train_days
        while start + test_days + forward_days < min_len:
            train_slice = slice(start - train_days, start)
            test_slice = slice(start, start + test_days)
            for name in frames:
                comps = component_cache[cache_key][name]
                is_m = _evaluate_window(comps.iloc[train_slice], weights, forward_days)
                oos_m = _evaluate_window(comps.iloc[test_slice], weights, forward_days)
                if is_m.samples >= 20:
                    is_hits.append(is_m.hit_rate)
                    is_ics.append(is_m.ic)
                    is_sharpes.append(is_m.sharpe)
                if oos_m.samples >= 10:
                    oos_hits.append(oos_m.hit_rate)
                    oos_ics.append(oos_m.ic)
                    oos_sharpes.append(oos_m.sharpe)
            folds += 1
            start += step_days

        def agg(hits, ics, sharpes) -> CalibrationMetrics:
            if not hits:
                return CalibrationMetrics(0.5, 0.0, 0.0, 0)
            return CalibrationMetrics(
                hit_rate=float(np.mean(hits)),
                ic=float(np.mean(ics)),
                sharpe=float(np.mean(sharpes)),
                samples=len(hits),
            )

        return agg(is_hits, is_ics, is_sharpes), agg(oos_hits, oos_ics, oos_sharpes), folds

    # 默认参数基线
    default_key = "i0|rsi30-70"
    default_is, default_oos, folds = eval_candidate(default_key, default_weights)
    default_obj = _objective(default_oos)

    best = {
        "key": default_key,
        "weights": default_weights,
        "is": default_is,
        "oos": default_oos,
        "obj": default_obj,
        "indicators": deepcopy(base_indicators),
        "thresholds": deepcopy(base_thresholds),
    }

    for ind_key, ind_override in enumerate(INDICATOR_CANDIDATES):
        indicators = _merge_indicators(base_indicators, ind_override)
        for rsi_os, rsi_ob in RSI_CANDIDATES:
            cache_key = f"i{ind_key}|rsi{rsi_os:.0f}-{rsi_ob:.0f}"
            thresholds = {
                **base_thresholds,
                "rsi_oversold": rsi_os,
                "rsi_overbought": rsi_ob,
            }
            for weights in WEIGHT_CANDIDATES:
                is_m, oos_m, _ = eval_candidate(cache_key, weights)
                obj = _objective(oos_m)
                # 轻度惩罚与默认偏离过大的方案
                drift = sum(abs(weights[k] - default_weights[k]) for k in WEIGHT_KEYS)
                obj -= 0.05 * drift
                if obj > best["obj"]:
                    best = {
                        "key": cache_key,
                        "weights": weights,
                        "is": is_m,
                        "oos": oos_m,
                        "obj": obj,
                        "indicators": indicators,
                        "thresholds": thresholds,
                    }

    shrunk_weights = _py_weights(
        _shrink_weights(best["weights"], default_weights, shrinkage)
    )
    existing_trend = dict(cfg.get("trend") or {})
    best_trend = {
        "default_horizon": existing_trend.get("default_horizon", "1m"),
        "indicators": {
            k: int(v) if isinstance(v, (int, float, np.integer, np.floating)) else v
            for k, v in best["indicators"].items()
        },
        "weights": shrunk_weights,
        "thresholds": {
            **dict(existing_trend.get("thresholds") or {}),
            **{k: float(v) for k, v in best["thresholds"].items()},
        },
    }
    if existing_trend.get("enhancements"):
        best_trend["enhancements"] = deepcopy(existing_trend["enhancements"])

    # 接受门槛：OOS 目标优于默认，且命中率/IC 不明显更差
    improve = float(best["obj"] - default_obj)
    accepted = (
        folds >= 2
        and best["oos"].samples >= 20
        and improve >= 0.02
        and best["oos"].hit_rate + 1e-9 >= default_oos.hit_rate - 0.01
    )
    if accepted:
        reason = (
            f"样本外目标提升 {improve:.3f}，已向默认收缩 {shrinkage:.0%} 后写回"
        )
    else:
        reason = (
            "未通过稳健性门槛（提升不足或样本不足），保留原参数；可查看候选结果"
        )

    if write_back and accepted:
        cfg["trend"] = best_trend
        cfg["calibration"] = {
            **cal_cfg,
            "years": float(years),
            "forward_days": int(forward_days),
            "train_days": int(train_days),
            "test_days": int(test_days),
            "step_days": int(step_days),
            "shrinkage": float(shrinkage),
            "last_run": {
                "accepted": True,
                "reason": reason,
                "indexes": list(frames.keys()),
                "folds": int(folds),
                "default_oos": _metrics_dict(default_oos),
                "best_oos": _metrics_dict(best["oos"]),
            },
        }
        save_config(cfg)

    lookback = int(np.median([len(df) for df in frames.values()]))
    return CalibrationResult(
        accepted=accepted,
        reason=reason,
        best_trend=best_trend,
        default_oos=default_oos,
        best_oos=best["oos"],
        best_is=best["is"],
        indexes_used=list(frames.keys()),
        lookback_days=lookback,
        forward_days=forward_days,
        folds=folds,
        shrinkage=shrinkage,
        details={
            "default_objective": round(float(default_obj), 4),
            "best_objective": round(float(best["obj"]), 4),
            "improvement": round(float(improve), 4),
            "raw_best_weights": _py_weights(best["weights"]),
            "shrunk_weights": shrunk_weights,
        },
    )
