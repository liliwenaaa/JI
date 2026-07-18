from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from jijin.engine.calibrate import (
    WEIGHT_CANDIDATES,
    _objective,
    _shrink_weights,
    calibrate_trend_strategy,
    CalibrationMetrics,
)


def _synth_ohlcv(n: int = 900, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.012, size=n)
    # mild trend persistence so some weight sets can beat random
    for i in range(1, n):
        rets[i] = 0.55 * rets[i] + 0.45 * rets[i - 1]
    close = 1000 * np.cumprod(1 + rets)
    volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    dates = pd.bdate_range("2018-01-01", periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": volume,
        }
    )


class TestCalibrate(unittest.TestCase):
    def test_shrink_weights_mixes_toward_default(self):
        best = {"ma": 1.0, "macd": 0.0, "rsi": 0.0, "momentum": 0.0, "volume": 0.0}
        defaults = {"ma": 0.2, "macd": 0.2, "rsi": 0.2, "momentum": 0.2, "volume": 0.2}
        mixed = _shrink_weights(best, defaults, 0.5)
        self.assertAlmostEqual(sum(mixed.values()), 1.0, places=6)
        self.assertGreater(mixed["ma"], mixed["macd"])

    def test_objective_prefers_better_hit_and_ic(self):
        weak = CalibrationMetrics(hit_rate=0.5, ic=0.0, sharpe=0.0, samples=100)
        strong = CalibrationMetrics(hit_rate=0.58, ic=0.08, sharpe=0.6, samples=100)
        self.assertGreater(_objective(strong), _objective(weak))

    def test_calibrate_runs_on_synthetic_frames(self):
        frames = {
            "A": _synth_ohlcv(900, seed=1),
            "B": _synth_ohlcv(900, seed=2),
            "C": _synth_ohlcv(900, seed=3),
        }
        cfg = {
            "valuation": {"watch_indexes": ["A", "B", "C"]},
            "trend": {"default_horizon": "1m"},
            "calibration": {
                "years": 4.0,
                "forward_days": 21,
                "train_days": 252,
                "test_days": 42,
                "step_days": 63,
                "shrinkage": 0.35,
            },
        }

        with patch(
            "jijin.engine.calibrate.load_calibration_frames",
            return_value=frames,
        ):
            result = calibrate_trend_strategy(cfg, write_back=False, force=False)

        self.assertGreaterEqual(result.folds, 2)
        self.assertEqual(set(result.indexes_used), {"A", "B", "C"})
        self.assertIn("weights", result.best_trend)
        self.assertAlmostEqual(
            sum(result.best_trend["weights"].values()), 1.0, places=5
        )
        self.assertTrue(set(result.best_trend["weights"]) >= set(WEIGHT_CANDIDATES[0]))


if __name__ == "__main__":
    unittest.main()
