from __future__ import annotations

import unittest

from jijin.engine.macro import evaluate_macro
from jijin.engine.settings import get_macro_settings, get_scoring_settings


class TestMacroEngine(unittest.TestCase):
    def test_expansion_and_easing_score_high(self):
        snap = evaluate_macro(
            cfg={"macro": {"policy": {"stance": "auto"}}},
            raw={
                "pmi": 52.5,
                "cpi": 1.8,
                "m2_yoy": 8.5,
                "m1_yoy": 5.0,
                "lpr_1y": 3.0,
                "lpr_1y_prev": 3.1,
                "errors": [],
            },
        )

        self.assertGreaterEqual(snap.macro_score, 65)
        self.assertEqual(snap.stance, "宽松")
        self.assertGreaterEqual(snap.policy_score, 70)

    def test_manual_policy_override(self):
        snap = evaluate_macro(
            cfg={"macro": {"policy": {"stance": "tightening", "manual_score": 28}}},
            raw={
                "pmi": 49.0,
                "cpi": 0.2,
                "m2_yoy": 6.5,
                "lpr_1y": 3.1,
                "lpr_1y_prev": 3.0,
                "errors": [],
            },
        )

        self.assertEqual(snap.stance, "偏紧")
        self.assertEqual(snap.policy_score, 28.0)

    def test_scoring_includes_macro_weights(self):
        settings = get_scoring_settings({})
        self.assertIn("macro", settings["weights"])
        self.assertIn("policy", settings["weights"])
        self.assertAlmostEqual(sum(settings["weights"].values()), 1.0)

    def test_macro_settings_defaults(self):
        settings = get_macro_settings({})
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["policy"]["stance"], "auto")


if __name__ == "__main__":
    unittest.main()
