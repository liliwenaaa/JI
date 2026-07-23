from __future__ import annotations

import unittest

from jijin.plugin import enabled_page_ids, load_plugins
from jijin.plugin.registry import PluginRegistry


class PluginRegistryTests(unittest.TestCase):
    def test_builtin_plugins_load(self) -> None:
        reg = PluginRegistry()
        load_plugins({}, reg=reg, reload=True)
        titles = [p.title for p in reg.sorted_pages()]
        self.assertEqual(
            titles,
            ["看板", "重点机会", "评分趋势", "智能仓位", "智能提醒", "持仓", "策略参数"],
        )
        self.assertIn("opportunity", reg.agents)
        self.assertIn("valuation_dynamic", reg.strategies)
        self.assertIn("smart", reg.alerts)
        self.assertIn("index_daily", reg.data_providers)

    def test_disable_page_via_config(self) -> None:
        reg = PluginRegistry()
        cfg = {"plugins": {"disabled": ["parameters"]}}
        load_plugins(cfg, reg=reg, reload=True)
        ids = enabled_page_ids(cfg, reg=reg)
        self.assertIsNotNone(ids)
        assert ids is not None
        self.assertNotIn("parameters", ids)
        self.assertIn("dashboard", ids)


if __name__ == "__main__":
    unittest.main()
