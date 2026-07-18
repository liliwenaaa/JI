from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_TREND_SETTINGS: dict[str, Any] = {
    "default_horizon": "1m",
    "indicators": {
        "ma_short": 20,
        "ma_medium": 60,
        "ma_long": 120,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "rsi_length": 14,
        "roc_length": 20,
        "adx_length": 14,
        "volatility_window": 60,
        "volume_window": 20,
    },
    "weights": {
        "ma": 0.30,
        "macd": 0.25,
        "rsi": 0.15,
        "momentum": 0.15,
        "volume": 0.15,
    },
    "thresholds": {
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "volume_expand_ratio": 1.20,
        "volume_contract_ratio": 0.80,
        "risk_volatility_medium": 22,
        "risk_volatility_high": 25,
        # 借鉴 Freqtrade / Regime-Aware：ADX 体制门控
        "adx_trend_min": 25,
        "adx_range_max": 20,
        "regime_range_shrink": 0.40,
        # Supertrend 确认（pandas-ta）
        "supertrend_length": 10,
        "supertrend_multiplier": 3.0,
        "supertrend_boost": 4.0,
        # 多周期对齐对概率的微调幅度
        "mtf_align_delta": 0.03,
    },
    "enhancements": {
        "soft_ma_score": True,
        "regime_filter": True,
        "supertrend_confirm": True,
        "multi_horizon_align": True,
    },
}

# 展望周期：用匹配该时间尺度的指标窗口估计方向性置信度（非点位预测）。
TREND_HORIZONS: dict[str, dict[str, Any]] = {
    "1d": {
        "label": "未来1天",
        "days": 1,
        "indicators": {
            "ma_short": 5,
            "ma_medium": 10,
            "ma_long": 20,
            "macd_fast": 6,
            "macd_slow": 13,
            "macd_signal": 5,
            "rsi_length": 7,
            "roc_length": 5,
            "adx_length": 7,
            "volatility_window": 20,
            "volume_window": 5,
        },
        "weights": {"ma": 0.20, "macd": 0.20, "rsi": 0.25, "momentum": 0.20, "volume": 0.15},
    },
    "1w": {
        "label": "未来1周",
        "days": 5,
        "indicators": {
            "ma_short": 5,
            "ma_medium": 10,
            "ma_long": 20,
            "macd_fast": 8,
            "macd_slow": 17,
            "macd_signal": 9,
            "rsi_length": 7,
            "roc_length": 5,
            "adx_length": 10,
            "volatility_window": 20,
            "volume_window": 5,
        },
        "weights": {"ma": 0.25, "macd": 0.20, "rsi": 0.20, "momentum": 0.20, "volume": 0.15},
    },
    "1m": {
        "label": "未来1个月",
        "days": 21,
        "indicators": {
            "ma_short": 10,
            "ma_medium": 20,
            "ma_long": 60,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "rsi_length": 14,
            "roc_length": 10,
            "adx_length": 14,
            "volatility_window": 40,
            "volume_window": 10,
        },
        "weights": {"ma": 0.30, "macd": 0.25, "rsi": 0.15, "momentum": 0.15, "volume": 0.15},
    },
    "3m": {
        "label": "未来3个月",
        "days": 63,
        "indicators": {
            "ma_short": 20,
            "ma_medium": 60,
            "ma_long": 120,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "rsi_length": 14,
            "roc_length": 20,
            "adx_length": 14,
            "volatility_window": 60,
            "volume_window": 20,
        },
        "weights": {"ma": 0.30, "macd": 0.25, "rsi": 0.15, "momentum": 0.15, "volume": 0.15},
    },
    "6m": {
        "label": "未来6个月",
        "days": 126,
        "indicators": {
            "ma_short": 20,
            "ma_medium": 60,
            "ma_long": 120,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "rsi_length": 21,
            "roc_length": 40,
            "adx_length": 21,
            "volatility_window": 90,
            "volume_window": 20,
        },
        "weights": {"ma": 0.35, "macd": 0.20, "rsi": 0.10, "momentum": 0.20, "volume": 0.15},
    },
    "1y": {
        "label": "未来1年",
        "days": 252,
        "indicators": {
            "ma_short": 60,
            "ma_medium": 120,
            "ma_long": 250,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "rsi_length": 21,
            "roc_length": 60,
            "adx_length": 21,
            "volatility_window": 120,
            "volume_window": 40,
        },
        "weights": {"ma": 0.40, "macd": 0.15, "rsi": 0.10, "momentum": 0.20, "volume": 0.15},
    },
}

DEFAULT_SCORING_SETTINGS: dict[str, Any] = {
    "weights": {
        "valuation": 0.25,
        "trend": 0.15,
        "capital": 0.12,
        "earnings": 0.12,
        "risk": 0.08,
        "sentiment": 0.08,
        "macro": 0.12,
        "policy": 0.08,
    },
    "labels": {
        "opportunity_min": 70,
        "neutral_min": 45,
    },
}

DEFAULT_MACRO_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "weights": {
        "pmi": 0.40,
        "cpi": 0.30,
        "liquidity": 0.30,
    },
    "thresholds": {
        "pmi_expansion": 50.0,
        "pmi_strong": 52.0,
        "cpi_low": 0.5,
        "cpi_comfort_high": 3.0,
        "cpi_high": 4.5,
        "m2_soft": 7.0,
        "m2_comfort": 9.0,
        "m2_hot": 12.0,
    },
    "policy": {
        "stance": "auto",  # auto / easing / neutral / tightening
        "manual_score": None,  # 0~100，非空时覆盖自动政策分
    },
}


def _deep_merge(defaults: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(defaults)
    for key, value in custom.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_weights(weights: dict[str, Any], defaults: dict[str, float]) -> dict[str, float]:
    """Clamp negative values and normalize configured weights to sum to one."""
    values = {
        key: max(0.0, float(weights.get(key, default)))
        for key, default in defaults.items()
    }
    total = sum(values.values())
    if total <= 0:
        return dict(defaults)
    return {key: value / total for key, value in values.items()}


def get_trend_settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    custom = (cfg or {}).get("trend") or {}
    settings = _deep_merge(DEFAULT_TREND_SETTINGS, custom)
    settings["weights"] = normalize_weights(
        settings["weights"], DEFAULT_TREND_SETTINGS["weights"]
    )
    horizon = str(settings.get("default_horizon") or "1m")
    if horizon not in TREND_HORIZONS:
        horizon = "1m"
    settings["default_horizon"] = horizon
    return settings


def list_trend_horizons() -> list[tuple[str, str, int]]:
    return [(key, meta["label"], int(meta["days"])) for key, meta in TREND_HORIZONS.items()]


def get_horizon_profile(horizon: str | None = None) -> dict[str, Any]:
    key = str(horizon or "1m")
    if key not in TREND_HORIZONS:
        key = "1m"
    profile = deepcopy(TREND_HORIZONS[key])
    profile["key"] = key
    return profile


def resolve_trend_settings_for_horizon(
    cfg: dict[str, Any] | None = None,
    horizon: str | None = None,
) -> dict[str, Any]:
    """合并用户趋势参数与所选展望周期。

    - 权重 / 阈值 / enhancements：始终用用户配置（校准与策略参数页才生效）
    - 指标窗口：默认展望周期用用户配置；其他周期用内置 horizon profile（匹配时间尺度）
    """
    base = get_trend_settings(cfg)
    profile = get_horizon_profile(horizon or base.get("default_horizon"))
    settings = deepcopy(base)
    horizon_key = profile["key"]
    default_key = str(base.get("default_horizon") or "1m")
    if horizon_key != default_key:
        settings["indicators"] = {
            **settings["indicators"],
            **(profile.get("indicators") or {}),
        }
    # 用户权重始终优先；不做 profile 覆盖
    settings["weights"] = normalize_weights(
        base.get("weights") or {}, DEFAULT_TREND_SETTINGS["weights"]
    )
    settings["horizon"] = horizon_key
    settings["horizon_label"] = profile["label"]
    settings["horizon_days"] = int(profile["days"])
    return settings


def get_scoring_settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    custom = (cfg or {}).get("scoring") or {}
    settings = _deep_merge(DEFAULT_SCORING_SETTINGS, custom)
    settings["weights"] = normalize_weights(
        settings["weights"], DEFAULT_SCORING_SETTINGS["weights"]
    )
    opportunity = float(settings["labels"]["opportunity_min"])
    neutral = float(settings["labels"]["neutral_min"])
    settings["labels"]["opportunity_min"] = min(100.0, max(0.0, opportunity))
    settings["labels"]["neutral_min"] = min(
        settings["labels"]["opportunity_min"], max(0.0, neutral)
    )
    return settings


def get_macro_settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    custom = (cfg or {}).get("macro") or {}
    settings = _deep_merge(DEFAULT_MACRO_SETTINGS, custom)
    settings["weights"] = normalize_weights(
        settings["weights"], DEFAULT_MACRO_SETTINGS["weights"]
    )
    settings["enabled"] = bool(settings.get("enabled", True))
    policy = dict(settings.get("policy") or {})
    stance = str(policy.get("stance") or "auto").lower()
    if stance not in {
        "auto",
        "自动",
        "easing",
        "宽松",
        "neutral",
        "中性",
        "tightening",
        "偏紧",
    }:
        stance = "auto"
    policy["stance"] = stance
    manual = policy.get("manual_score")
    if manual is not None and manual != "":
        policy["manual_score"] = float(np_clip(manual, 0, 100))
    else:
        policy["manual_score"] = None
    settings["policy"] = policy
    return settings


def np_clip(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))
