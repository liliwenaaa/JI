from __future__ import annotations

import unittest

from jijin.engine.settings import (
    get_scoring_settings,
    get_trend_settings,
    resolve_trend_settings_for_horizon,
)


class TestEngineSettings(unittest.TestCase):
    def test_trend_weights_are_normalized(self):
        settings = get_trend_settings(
            {"trend": {"weights": {"ma": 4, "macd": 1, "rsi": 0, "momentum": 0, "volume": 0}}}
        )

        self.assertAlmostEqual(sum(settings["weights"].values()), 1.0)
        self.assertAlmostEqual(settings["weights"]["ma"], 0.8)
        self.assertAlmostEqual(settings["weights"]["macd"], 0.2)

    def test_scoring_thresholds_are_ordered(self):
        settings = get_scoring_settings(
            {
                "scoring": {
                    "labels": {
                        "neutral_min": 80,
                        "opportunity_min": 60,
                    }
                }
            }
        )

        self.assertEqual(settings["labels"]["opportunity_min"], 60)
        self.assertEqual(settings["labels"]["neutral_min"], 60)

    def test_partial_config_keeps_defaults(self):
        settings = get_trend_settings(
            {"trend": {"indicators": {"rsi_length": 21}}}
        )

        self.assertEqual(settings["indicators"]["rsi_length"], 21)
        self.assertEqual(settings["indicators"]["ma_short"], 20)

    def test_user_weights_survive_horizon_resolve(self):
        settings = resolve_trend_settings_for_horizon(
            {
                "trend": {
                    "default_horizon": "1m",
                    "weights": {
                        "ma": 0.5,
                        "macd": 0.2,
                        "rsi": 0.1,
                        "momentum": 0.1,
                        "volume": 0.1,
                    },
                }
            },
            horizon="1m",
        )
        self.assertAlmostEqual(settings["weights"]["ma"], 0.5)
        other = resolve_trend_settings_for_horizon(
            {"trend": {"default_horizon": "1m", "weights": settings["weights"]}},
            horizon="1d",
        )
        self.assertAlmostEqual(other["weights"]["ma"], 0.5)
        self.assertEqual(other["indicators"]["ma_short"], 5)


if __name__ == "__main__":
    unittest.main()
