from __future__ import annotations

import unittest

from jijin.data.market import INDEX_GROUPS, INDEX_SYMBOLS, list_index_names


class TestMarketIndexes(unittest.TestCase):
    def test_expanded_universe_has_industry_indexes(self):
        self.assertGreaterEqual(len(INDEX_SYMBOLS), 40)
        for name in ("中证消费", "中证医药", "证券公司", "科创50", "新能源车"):
            self.assertIn(name, INDEX_SYMBOLS)

    def test_symbols_are_unique(self):
        symbols = list(INDEX_SYMBOLS.values())
        self.assertEqual(len(symbols), len(set(symbols)))

    def test_groups_cover_only_known_indexes(self):
        for group, names in INDEX_GROUPS.items():
            for name in names:
                self.assertIn(name, INDEX_SYMBOLS, msg=f"{group}/{name}")
        grouped = {n for names in INDEX_GROUPS.values() for n in names}
        self.assertEqual(grouped, set(INDEX_SYMBOLS))

    def test_list_by_group(self):
        tech = list_index_names(group="科技成长")
        self.assertIn("半导体", tech)
        self.assertNotIn("沪深300", tech)


if __name__ == "__main__":
    unittest.main()
