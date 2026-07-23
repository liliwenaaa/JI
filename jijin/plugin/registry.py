"""全局插件注册表。"""
from __future__ import annotations

from typing import Iterable

from jijin.plugin.base import (
    AgentSpec,
    AlertSpec,
    DataProviderSpec,
    PageSpec,
    StrategySpec,
)


class PluginRegistry:
    """进程内插件中心：页面 / Agent / 策略 / 提醒 / 数据源。"""

    def __init__(self) -> None:
        self.pages: dict[str, PageSpec] = {}
        self.agents: dict[str, AgentSpec] = {}
        self.strategies: dict[str, StrategySpec] = {}
        self.alerts: dict[str, AlertSpec] = {}
        self.data_providers: dict[str, DataProviderSpec] = {}
        self._loaded = False

    def register_page(self, spec: PageSpec, *, replace: bool = False) -> None:
        if not replace and spec.id in self.pages:
            raise ValueError(f"页面插件已存在: {spec.id}")
        self.pages[spec.id] = spec

    def register_agent(self, spec: AgentSpec, *, replace: bool = False) -> None:
        if not replace and spec.id in self.agents:
            raise ValueError(f"Agent 插件已存在: {spec.id}")
        self.agents[spec.id] = spec

    def register_strategy(self, spec: StrategySpec, *, replace: bool = False) -> None:
        if not replace and spec.id in self.strategies:
            raise ValueError(f"策略插件已存在: {spec.id}")
        self.strategies[spec.id] = spec

    def register_alert(self, spec: AlertSpec, *, replace: bool = False) -> None:
        if not replace and spec.id in self.alerts:
            raise ValueError(f"提醒插件已存在: {spec.id}")
        self.alerts[spec.id] = spec

    def register_data_provider(self, spec: DataProviderSpec, *, replace: bool = False) -> None:
        if not replace and spec.id in self.data_providers:
            raise ValueError(f"数据源插件已存在: {spec.id}")
        self.data_providers[spec.id] = spec

    def sorted_pages(self, enabled: Iterable[str] | None = None) -> list[PageSpec]:
        allow = set(enabled) if enabled is not None else None
        pages = [
            p
            for p in self.pages.values()
            if allow is None or p.id in allow
        ]
        return sorted(pages, key=lambda p: (p.order, p.title))

    def page_titles(self, enabled: Iterable[str] | None = None) -> list[str]:
        return [p.title for p in self.sorted_pages(enabled)]

    def page_by_title(self, title: str) -> PageSpec | None:
        for p in self.pages.values():
            if p.title == title:
                return p
        return None

    def page_by_load_kind(self, kind: str) -> PageSpec | None:
        for p in self.pages.values():
            if p.load_kind == kind:
                return p
        return None

    def get_agent(self, agent_id: str) -> AgentSpec:
        if agent_id not in self.agents:
            raise KeyError(f"未知 Agent: {agent_id}")
        return self.agents[agent_id]

    def clear(self) -> None:
        self.pages.clear()
        self.agents.clear()
        self.strategies.clear()
        self.alerts.clear()
        self.data_providers.clear()
        self._loaded = False


# 进程单例
registry = PluginRegistry()
