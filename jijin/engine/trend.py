from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from jijin.data.market import fetch_index_daily
from jijin.engine.settings import (
    list_trend_horizons,
    resolve_trend_settings_for_horizon,
)


@dataclass
class TrendResult:
    index: str
    score: float  # 0~100，越高越偏多
    risk_level: str  # 低 / 中 / 高
    probability_up: float  # 该展望周期内偏多方向置信度 0~1
    ma_signal: str
    macd_signal: str
    rsi: float | None
    volatility: float | None  # 年化波动
    momentum_20d: float | None
    volume_trend: str
    strength: float  # 趋势强度 0~100
    horizon: str = "1m"
    horizon_label: str = "未来1个月"
    horizon_days: int = 21
    move_band_pct: float | None = None  # 该周期 1σ 波动带宽（%）
    bias: str = "中性"  # 偏多 / 中性 / 偏空
    details: dict[str, Any] = field(default_factory=dict)


_HORIZON_ORDER = ("1d", "1w", "1m", "3m", "6m", "1y")


def _horizon_probability(score: float, days: int) -> float:
    """周期越长，置信度向 0.5 收缩（均值回归不确定性上升）。"""
    raw = float(np.clip(0.2 + score / 100 * 0.6, 0.15, 0.85))
    shrink = float(np.clip(np.log1p(max(days, 1)) / np.log1p(252) * 0.55, 0.0, 0.75))
    return float(np.clip(0.5 + (raw - 0.5) * (1.0 - shrink), 0.15, 0.85))


def _bias_from_probability(probability_up: float) -> str:
    if probability_up >= 0.58:
        return "偏多"
    if probability_up <= 0.42:
        return "偏空"
    return "中性"


def _enhancement_flags(settings: dict[str, Any]) -> dict[str, bool]:
    defaults = {
        "soft_ma_score": True,
        "regime_filter": True,
        "supertrend_confirm": True,
        "multi_horizon_align": True,
    }
    custom = settings.get("enhancements") or {}
    return {k: bool(custom.get(k, v)) for k, v in defaults.items()}


def _soft_ma_score(
    last_close: float,
    last_ma_short: float,
    last_ma_medium: float,
    discrete_score: float,
) -> float:
    """离散排列信号 + 相对中期均线偏离的连续分，减轻穿越抖动。"""
    if last_ma_medium <= 0:
        return discrete_score
    pct = (last_close / last_ma_medium - 1.0) * 100.0
    soft = float(np.clip(50.0 + pct * 8.0, 15.0, 85.0))
    # 短均线相对中均线再给一点斜率信息
    if last_ma_short > last_ma_medium:
        soft = min(95.0, soft + 3.0)
    elif last_ma_short < last_ma_medium:
        soft = max(5.0, soft - 3.0)
    return float(0.55 * discrete_score + 0.45 * soft)


def _classify_regime(adx: float, thresholds: dict[str, Any]) -> str:
    trend_min = float(thresholds.get("adx_trend_min", 25))
    range_max = float(thresholds.get("adx_range_max", 20))
    if adx >= trend_min:
        return "趋势"
    if adx <= range_max:
        return "震荡"
    return "过渡"


def _apply_regime_shrink(
    score: float,
    regime: str,
    thresholds: dict[str, Any],
) -> float:
    """震荡市向中性收缩（Regime-Aware / ADX 过滤共识）。"""
    if regime != "震荡":
        return score
    shrink = float(np.clip(thresholds.get("regime_range_shrink", 0.40), 0.0, 0.9))
    return float(50.0 + (score - 50.0) * (1.0 - shrink))


def _supertrend_direction(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    thresholds: dict[str, Any],
) -> tuple[int | None, float | None]:
    length = int(thresholds.get("supertrend_length", 10))
    multiplier = float(thresholds.get("supertrend_multiplier", 3.0))
    if len(close) < length + 5:
        return None, None
    st = ta.supertrend(high, low, close, length=length, multiplier=multiplier)
    if st is None or st.empty:
        return None, None
    dir_col = f"SUPERTd_{length}_{multiplier}"
    line_col = f"SUPERT_{length}_{multiplier}"
    if dir_col not in st.columns:
        # 兼容部分版本列名格式
        candidates = [c for c in st.columns if str(c).startswith("SUPERTd_")]
        dir_col = candidates[0] if candidates else ""
    if not dir_col or dir_col not in st.columns:
        return None, None
    raw = st[dir_col].iloc[-1]
    if pd.isna(raw):
        return None, None
    direction = int(raw)  # 1 多 / -1 空
    line = float(st[line_col].iloc[-1]) if line_col in st.columns and pd.notna(st[line_col].iloc[-1]) else None
    return direction, line


def _apply_supertrend_confirm(
    score: float,
    direction: int | None,
    thresholds: dict[str, Any],
) -> float:
    if direction is None:
        return score
    boost = float(thresholds.get("supertrend_boost", 4.0))
    bullish = direction >= 1
    if bullish:
        # 与偏多一致则加分；与偏空冲突则小幅拉回
        delta = boost if score >= 50 else -0.5 * boost
    else:
        delta = -boost if score <= 50 else 0.5 * boost
    return float(np.clip(score + delta, 0.0, 100.0))


def apply_multi_horizon_alignment(
    results: list[TrendResult],
    *,
    delta: float = 0.03,
) -> list[TrendResult]:
    """借鉴 Freqtrade informative MTF：更长周期方向一致时增强置信度，冲突则收缩。"""
    if len(results) < 2:
        return results

    by_key = {r.horizon: r for r in results}
    order = [k for k in _HORIZON_ORDER if k in by_key]
    adjusted: list[TrendResult] = []
    for key in order:
        current = by_key[key]
        idx = order.index(key)
        longer = [by_key[k] for k in order[idx + 1 :]]
        if not longer or current.bias == "中性":
            details = dict(current.details)
            details["mtf_align"] = "skip"
            adjusted.append(replace(current, details=details))
            continue

        agree = sum(1 for x in longer if x.bias == current.bias)
        conflict = sum(
            1
            for x in longer
            if x.bias != "中性" and x.bias != current.bias
        )
        adj = 0.0
        if agree:
            adj = float(delta) * min(agree, 2)
            if current.bias == "偏空":
                adj = -adj
        if conflict:
            # 与更长周期冲突：向 0.5 收缩
            pull = float(delta) * min(conflict, 2)
            if current.probability_up > 0.5:
                adj -= pull
            else:
                adj += pull

        new_p = float(np.clip(current.probability_up + adj, 0.15, 0.85))
        details = dict(current.details)
        details["mtf_align"] = {
            "agree": agree,
            "conflict": conflict,
            "delta": round(adj, 4),
            "probability_before": current.probability_up,
        }
        adjusted.append(
            replace(
                current,
                probability_up=round(new_p, 3),
                bias=_bias_from_probability(new_p),
                details=details,
            )
        )
    # 保持原 horizons 请求顺序
    out_map = {r.horizon: r for r in adjusted}
    return [out_map.get(r.horizon, r) for r in results]


def compute_trend_from_ohlcv(
    df: pd.DataFrame,
    index_name: str = "",
    settings: dict[str, Any] | None = None,
    horizon: str | None = None,
) -> TrendResult:
    settings = settings or resolve_trend_settings_for_horizon(horizon=horizon)

    indicators = settings["indicators"]
    weights = settings["weights"]
    thresholds = settings["thresholds"]
    flags = _enhancement_flags(settings)
    horizon_key = str(settings.get("horizon") or horizon or "1m")
    horizon_label = str(settings.get("horizon_label") or "未来1个月")
    horizon_days = int(settings.get("horizon_days") or 21)

    ma_short_length = int(indicators["ma_short"])
    ma_medium_length = int(indicators["ma_medium"])
    ma_long_length = int(indicators["ma_long"])
    macd_fast = int(indicators["macd_fast"])
    macd_slow = int(indicators["macd_slow"])
    macd_signal_length = int(indicators["macd_signal"])
    rsi_length = int(indicators["rsi_length"])
    roc_length = int(indicators["roc_length"])
    adx_length = int(indicators["adx_length"])
    volatility_window = int(indicators["volatility_window"])
    volume_window = int(indicators["volume_window"])

    minimum_sample = max(
        ma_medium_length,
        macd_slow + macd_signal_length,
        rsi_length + 1,
        roc_length + 1,
        volatility_window,
        volume_window * 2,
        30,
    )
    if df is None or len(df) < minimum_sample:
        return TrendResult(
            index=index_name,
            score=50.0,
            risk_level="中",
            probability_up=0.5,
            ma_signal="数据不足",
            macd_signal="数据不足",
            rsi=None,
            volatility=None,
            momentum_20d=None,
            volume_trend="未知",
            strength=0.0,
            horizon=horizon_key,
            horizon_label=horizon_label,
            horizon_days=horizon_days,
            move_band_pct=None,
            bias="中性",
            details={"error": "样本不足", "minimum_sample": minimum_sample},
        )

    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df.get("high", close), errors="coerce")
    low = pd.to_numeric(df.get("low", close), errors="coerce")
    volume = (
        pd.to_numeric(df["volume"], errors="coerce")
        if "volume" in df.columns
        else pd.Series(np.nan, index=df.index)
    )

    ma_short = ta.sma(close, length=ma_short_length)
    ma_medium = ta.sma(close, length=ma_medium_length)
    ma_long = (
        ta.sma(close, length=ma_long_length)
        if len(close) >= ma_long_length
        else ma_medium
    )
    macd = ta.macd(
        close, fast=macd_fast, slow=macd_slow, signal=macd_signal_length
    )
    rsi = ta.rsi(close, length=rsi_length)
    momentum = ta.roc(close, length=roc_length)
    adx = ta.adx(high, low, close, length=adx_length)

    if macd is None or macd.empty:
        macd_hist = pd.Series(np.nan, index=close.index)
    else:
        macd_hist = macd[f"MACDh_{macd_fast}_{macd_slow}_{macd_signal_length}"]

    if adx is None or adx.empty:
        adx_series = pd.Series(np.nan, index=close.index)
    else:
        adx_series = adx[f"ADX_{adx_length}"]

    ret = close.pct_change()
    recent_returns = ret.tail(volatility_window)
    vol = (
        float(recent_returns.std() * np.sqrt(252) * 100)
        if recent_returns.notna().sum() > 10
        else None
    )
    mom20 = (
        float(momentum.iloc[-1])
        if momentum is not None and pd.notna(momentum.iloc[-1])
        else None
    )

    last_close = float(close.iloc[-1])
    last_ma_short = float(ma_short.iloc[-1])
    last_ma_medium = float(ma_medium.iloc[-1])
    last_ma_long = (
        float(ma_long.iloc[-1]) if pd.notna(ma_long.iloc[-1]) else last_ma_medium
    )

    if last_close > last_ma_short > last_ma_medium:
        ma_signal = "多头排列"
        ma_score = 80.0
    elif last_close < last_ma_short < last_ma_medium:
        ma_signal = "空头排列"
        ma_score = 20.0
    elif last_close > last_ma_medium:
        ma_signal = "站上中期均线"
        ma_score = 65.0
    else:
        ma_signal = "跌破中期均线"
        ma_score = 35.0

    if flags["soft_ma_score"]:
        ma_score = _soft_ma_score(
            last_close, last_ma_short, last_ma_medium, ma_score
        )

    hist = float(macd_hist.iloc[-1])
    hist_prev = float(macd_hist.iloc[-2])
    if hist > 0 and hist > hist_prev:
        macd_signal = "红柱放大"
        macd_score = 75
    elif hist > 0:
        macd_signal = "零轴上方"
        macd_score = 60
    elif hist < 0 and hist < hist_prev:
        macd_signal = "绿柱放大"
        macd_score = 25
    else:
        macd_signal = "零轴下方"
        macd_score = 40

    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0
    if last_rsi >= float(thresholds["rsi_overbought"]):
        rsi_score = 35
    elif last_rsi <= float(thresholds["rsi_oversold"]):
        rsi_score = 70
    else:
        rsi_score = 40 + (last_rsi - 50) * 0.8

    vol_score = 50
    volume_trend = "平稳"
    if volume.notna().sum() > volume_window * 2:
        v1 = float(volume.tail(volume_window).mean())
        v0 = float(volume.iloc[-volume_window * 2 : -volume_window].mean())
        if v0 > 0:
            ratio = v1 / v0
            if ratio > float(thresholds["volume_expand_ratio"]) and mom20 and mom20 > 0:
                volume_trend = "放量上涨"
                vol_score = 70
            elif ratio > float(thresholds["volume_expand_ratio"]) and mom20 and mom20 < 0:
                volume_trend = "放量下跌"
                vol_score = 30
            elif ratio < float(thresholds["volume_contract_ratio"]):
                volume_trend = "缩量"
                vol_score = 45
            else:
                volume_trend = "量能平稳"
                vol_score = 55

    mom_score = 50
    if mom20 is not None:
        mom_score = float(np.clip(50 + mom20 * 2, 5, 95))

    last_adx = float(adx_series.iloc[-1]) if pd.notna(adx_series.iloc[-1]) else 0.0
    strength = float(np.clip(last_adx * 2, 0, 100))
    regime = _classify_regime(last_adx, thresholds)

    score = float(
        np.clip(
            weights["ma"] * ma_score
            + weights["macd"] * macd_score
            + weights["rsi"] * rsi_score
            + weights["momentum"] * mom_score
            + weights["volume"] * vol_score,
            0,
            100,
        )
    )

    st_dir, st_line = (None, None)
    if flags["supertrend_confirm"]:
        st_dir, st_line = _supertrend_direction(high, low, close, thresholds)
        score = _apply_supertrend_confirm(score, st_dir, thresholds)

    if flags["regime_filter"]:
        score = _apply_regime_shrink(score, regime, thresholds)

    score = float(np.clip(score, 0, 100))

    if (
        vol is not None
        and vol > float(thresholds["risk_volatility_high"])
        and score < 40
    ):
        risk_level = "高"
    elif vol is not None and vol > float(thresholds["risk_volatility_medium"]):
        risk_level = "中"
    elif score < 35:
        risk_level = "中"
    else:
        risk_level = "低" if score >= 60 else "中"

    probability_up = _horizon_probability(score, horizon_days)
    move_band = None if vol is None else round(vol * float(np.sqrt(horizon_days / 252)), 2)
    bias = _bias_from_probability(probability_up)

    return TrendResult(
        index=index_name,
        score=round(score, 1),
        risk_level=risk_level,
        probability_up=round(probability_up, 3),
        ma_signal=ma_signal,
        macd_signal=macd_signal,
        rsi=round(last_rsi, 1),
        volatility=None if vol is None else round(vol, 2),
        momentum_20d=None if mom20 is None else round(mom20, 2),
        volume_trend=volume_trend,
        strength=round(strength, 1),
        horizon=horizon_key,
        horizon_label=horizon_label,
        horizon_days=horizon_days,
        move_band_pct=move_band,
        bias=bias,
        details={
            "indicator_backend": "pandas-ta-classic",
            "close": round(last_close, 2),
            "ma_short": round(last_ma_short, 2),
            "ma_medium": round(last_ma_medium, 2),
            "ma_long": round(last_ma_long, 2),
            "macd_hist": round(hist, 4),
            "adx14": round(last_adx, 2),
            "regime": regime,
            "supertrend_dir": st_dir,
            "supertrend_line": None if st_line is None else round(st_line, 2),
            "roc_length": roc_length,
            "indicator_settings": indicators,
            "score_weights": weights,
            "thresholds": thresholds,
            "enhancements": flags,
            "horizon": horizon_key,
            "horizon_label": horizon_label,
            "horizon_days": horizon_days,
        },
    )


def analyze_trend(
    index_name: str,
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    horizon: str | None = None,
) -> TrendResult:
    from jijin.config import load_config

    cfg = cfg or load_config()
    settings = resolve_trend_settings_for_horizon(cfg, horizon=horizon)
    df = fetch_index_daily(index_name, cfg=cfg, force=force)
    return compute_trend_from_ohlcv(
        df,
        index_name=index_name,
        settings=settings,
    )


def analyze_trend_horizons(
    index_name: str,
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    horizons: list[str] | None = None,
) -> list[TrendResult]:
    from jijin.config import load_config

    cfg = cfg or load_config()
    df = fetch_index_daily(index_name, cfg=cfg, force=force)
    keys = horizons or [key for key, _, _ in list_trend_horizons()]
    results: list[TrendResult] = []
    for key in keys:
        settings = resolve_trend_settings_for_horizon(cfg, horizon=key)
        results.append(
            compute_trend_from_ohlcv(df, index_name=index_name, settings=settings)
        )

    base = resolve_trend_settings_for_horizon(cfg)
    flags = _enhancement_flags(base)
    if flags["multi_horizon_align"]:
        delta = float((base.get("thresholds") or {}).get("mtf_align_delta", 0.03))
        results = apply_multi_horizon_alignment(results, delta=delta)
    return results
