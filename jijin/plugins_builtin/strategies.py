"""内置策略模板插件。"""
from __future__ import annotations

from jijin.plugin.base import StrategySpec
from jijin.plugin.registry import PluginRegistry
from jijin.strategy.generator import STRATEGY_TEMPLATES


def register(reg: PluginRegistry) -> None:
    for sid, meta in STRATEGY_TEMPLATES.items():
        reg.register_strategy(
            StrategySpec(
                id=str(sid),
                label=str(meta.get("label") or sid),
                template=dict(meta),
                description=str(meta.get("desc") or ""),
            ),
            replace=True,
        )
