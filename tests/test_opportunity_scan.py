from __future__ import annotations

import unittest
from unittest.mock import patch

from jijin.engine.trend import TrendResult
from jijin.screener.opportunity import scan_index_opportunities


def _trend(name: str, prob: float, score: float = 60.0) -> TrendResult:
    return TrendResult(
        index=name,
        score=score,
        risk_level="中",
        probability_up=prob,
        ma_signal="多头排列",
        macd_signal="零轴上方",
        rsi=55.0,
        volatility=18.0,
        momentum_20d=2.0,
        volume_trend="量能平稳",
        strength=40.0,
        horizon="1m",
        horizon_label="未来1个月",
        horizon_days=21,
        move_band_pct=5.0,
        bias="偏多" if prob >= 0.58 else ("偏空" if prob <= 0.42 else "中性"),
    )


class TestIndexOpportunityScan(unittest.TestCase):
    def test_ranks_by_probability_and_returns_top_n(self):
        probs = {
            "沪深300": 0.55,
            "中证500": 0.72,
            "中证1000": 0.68,
            "上证50": 0.40,
            "创业板50": 0.80,
        }

        def fake_analyze(name, cfg=None, force=False, horizon=None):
            return _trend(name, probs.get(name, 0.5))

        with patch("jijin.screener.opportunity.analyze_trend", side_effect=fake_analyze), patch(
            "jijin.screener.opportunity.market_index_universe",
            return_value=list(probs.keys()),
        ):
            result = scan_index_opportunities(cfg={}, force=False, top_n=3)

        self.assertEqual([r.index for r in result], ["创业板50", "中证500", "中证1000"])
        self.assertEqual(result[0].rank, 1)
        self.assertAlmostEqual(result[0].probability_up, 0.80)


if __name__ == "__main__":
    unittest.main()
