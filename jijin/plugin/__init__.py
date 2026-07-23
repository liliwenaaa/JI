"""插件化扩展点：页面 / Agent / 策略 / 提醒 / 数据源。"""
from __future__ import annotations

from jijin.plugin.base import (
    AgentSpec,
    AlertSpec,
    DataProviderSpec,
    PageSpec,
    StrategySpec,
)
from jijin.plugin.loader import discover_entry_points, enabled_page_ids, load_plugins, plugin_config
from jijin.plugin.registry import PluginRegistry, registry

__all__ = [
    "AgentSpec",
    "AlertSpec",
    "DataProviderSpec",
    "PageSpec",
    "PluginRegistry",
    "StrategySpec",
    "discover_entry_points",
    "enabled_page_ids",
    "load_plugins",
    "plugin_config",
    "registry",
]
