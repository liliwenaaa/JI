from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from jijin.engine.settings import list_trend_horizons, resolve_trend_settings_for_horizon
from jijin.engine.trend import (
    TrendResult,
    _horizon_probability,
    apply_multi_horizon_alignment,
    compute_trend_from_ohlcv,
)


class TestTrendEngine(unittest.TestCase):
    @staticmethod
    def _ohlcv(closes: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": closes - 0.2,
                "high": closes + 0.8,
                "low": closes - 0.8,
                "close": closes,
                "volume": np.linspace(1_000_000, 1_500_000, len(closes)),
            }
        )

    def test_uptrend_uses_pandas_ta_backend(self):
        closes = np.linspace(100, 160, 180)
        result = compute_trend_from_ohlcv(
            self._ohlcv(closes),
            "测试指数",
            settings=resolve_trend_settings_for_horizon(horizon="1m"),
        )

        self.assertEqual(result.details["indicator_backend"], "pandas-ta-classic")
        self.assertEqual(result.ma_signal, "多头排列")
        self.assertGreater(result.score, 50)
        self.assertGreater(result.probability_up, 0.5)
        self.assertEqual(result.horizon, "1m")
        self.assertIn(result.bias, {"偏多", "中性"})
        self.assertIn("adx14", result.details)
        self.assertIn(result.details.get("regime"), {"趋势", "过渡", "震荡"})
        self.assertIn("supertrend_dir", result.details)

    def test_short_sample_returns_neutral(self):
        result = compute_trend_from_ohlcv(
            self._ohlcv(np.linspace(100, 105, 30)),
            settings=resolve_trend_settings_for_horizon(horizon="1m"),
        )

        self.assertEqual(result.score, 50.0)
        self.assertEqual(result.details["error"], "样本不足")

    def test_horizons_are_available(self):
        keys = [key for key, _, _ in list_trend_horizons()]
        self.assertEqual(keys, ["1d", "1w", "1m", "3m", "6m", "1y"])

    def test_longer_horizon_shrinks_confidence_mapping(self):
        short = _horizon_probability(80, days=1)
        long = _horizon_probability(80, days=252)
        self.assertGreater(short, long)
        self.assertGreater(long, 0.5)

    def test_horizon_outputs_move_band(self):
        closes = np.linspace(100, 180, 320)
        long = compute_trend_from_ohlcv(
            self._ohlcv(closes),
            "测试",
            settings=resolve_trend_settings_for_horizon(horizon="1y"),
        )
        self.assertEqual(long.horizon_label, "未来1年")
        self.assertIsNotNone(long.move_band_pct)
        self.assertGreater(long.move_band_pct or 0, 0)

    def test_range_regime_shrinks_extreme_score(self):
        # 低波动震荡：ADX 通常偏低，体制门控应把极端分往 50 拉
        rng = np.random.default_rng(0)
        noise = rng.normal(0, 0.003, 220)
        closes = 100 * np.cumprod(1 + noise)
        settings = resolve_trend_settings_for_horizon(horizon="1m")
        on = compute_trend_from_ohlcv(self._ohlcv(closes), settings=settings)
        settings_off = resolve_trend_settings_for_horizon(horizon="1m")
        settings_off["enhancements"] = {
            **settings_off.get("enhancements", {}),
            "regime_filter": False,
            "supertrend_confirm": False,
        }
        off = compute_trend_from_ohlcv(self._ohlcv(closes), settings=settings_off)
        if on.details.get("regime") == "震荡":
            self.assertLessEqual(abs(on.score - 50), abs(off.score - 50) + 1e-6)

    def test_multi_horizon_alignment_pulls_conflict_toward_neutral(self):
        short = TrendResult(
            index="x",
            score=80,
            risk_level="低",
            probability_up=0.72,
            ma_signal="多头排列",
            macd_signal="红柱放大",
            rsi=60,
            volatility=15,
            momentum_20d=5,
            volume_trend="平稳",
            strength=40,
            horizon="1d",
            bias="偏多",
            details={},
        )
        long = TrendResult(
            index="x",
            score=25,
            risk_level="中",
            probability_up=0.30,
            ma_signal="空头排列",
            macd_signal="绿柱放大",
            rsi=35,
            volatility=18,
            momentum_20d=-4,
            volume_trend="平稳",
            strength=50,
            horizon="1m",
            bias="偏空",
            details={},
        )
        out = apply_multi_horizon_alignment([short, long], delta=0.03)
        short_out = next(r for r in out if r.horizon == "1d")
        self.assertLess(short_out.probability_up, short.probability_up)
        self.assertIn("mtf_align", short_out.details)


if __name__ == "__main__":
    unittest.main()
