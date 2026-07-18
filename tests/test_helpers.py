from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jijin.alert.position import map_percentile_to_target
from jijin.data.fund import _guess_index_from_name, _share_class


class TestHelpers(unittest.TestCase):
    def test_share_class(self):
        self.assertEqual(_share_class("易方达沪深300ETF联接A"), "A")
        self.assertEqual(_share_class("某指数C"), "C")

    def test_guess_index(self):
        self.assertEqual(_guess_index_from_name("易方达中证500ETF联接A"), "中证500")
        self.assertEqual(_guess_index_from_name("华夏创业板ETF联接"), "创业板指")

    def test_band_mapping(self):
        bands = [
            {"max_percentile": 20, "label": "低估", "target_pct": 90},
            {"max_percentile": 40, "label": "偏低", "target_pct": 70},
            {"max_percentile": 60, "label": "适中", "target_pct": 50},
            {"max_percentile": 80, "label": "偏高", "target_pct": 30},
            {"max_percentile": 100, "label": "高估", "target_pct": 15},
        ]
        self.assertEqual(map_percentile_to_target(10, bands), ("低估", 90))
        self.assertEqual(map_percentile_to_target(55, bands), ("适中", 50))
        self.assertEqual(map_percentile_to_target(95, bands), ("高估", 15))


if __name__ == "__main__":
    unittest.main()
