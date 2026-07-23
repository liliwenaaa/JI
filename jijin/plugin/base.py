"""插件化扩展点：页面 / Agent / 策略 / 提醒 / 数据源。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

ProgressCb = Callable[[int, int, str], None]
LoadFn = Callable[[ProgressCb], dict[str, Any]]
PageRender = Callable[[dict[str, Any]], None]
NeedsDataFn = Callable[[dict[str, Any]], bool]
BuildLoadFn = Callable[[dict[str, Any], dict[str, Any] | None], tuple[str, LoadFn]]

__all__ = [
    "AgentSpec",
    "AlertSpec",
    "BuildLoadFn",
    "DataProviderSpec",
    "LoadFn",
    "NeedsDataFn",
    "PagePlugin",
    "PageRender",
    "PageSpec",
    "ProgressCb",
    "StrategySpec",
]

@runtime_checkable
class PagePlugin(Protocol):
    """UI 页面插件。"""

    id: str
    title: str
    order: int

    def render(self, cfg: dict[str, Any]) -> None: ...

    def needs_data(self, cfg: dict[str, Any]) -> bool: ...

    def build_load(
        self,
        cfg: dict[str, Any],
        job: dict[str, Any] | None,
    ) -> tuple[str, LoadFn] | None: ...


@dataclass(frozen=True)
class PageSpec:
    """声明式页面插件（推荐实现方式）。"""

    id: str
    title: str
    render: PageRender = field(repr=False)
    order: int = 100
    needs_data: NeedsDataFn | None = field(default=None, repr=False)
    build_load: BuildLoadFn | None = field(default=None, repr=False)
    load_kind: str | None = None
    description: str = ""

    def needs_data_or_false(self, cfg: dict[str, Any]) -> bool:
        if self.needs_data is None:
            return False
        return bool(self.needs_data(cfg))

    def build_load_or_none(
        self,
        cfg: dict[str, Any],
        job: dict[str, Any] | None,
    ) -> tuple[str, LoadFn] | None:
        if self.build_load is None:
            return None
        return self.build_load(cfg, job)


@dataclass(frozen=True)
class AgentSpec:
    """业务 Agent 插件。"""

    id: str
    run: Callable[..., Any] = field(repr=False)
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategySpec:
    """仓位策略模板插件。"""

    id: str
    label: str
    template: dict[str, Any]
    description: str = ""


@dataclass(frozen=True)
class AlertSpec:
    """提醒生成器插件。"""

    id: str
    run: Callable[..., Any] = field(repr=False)
    description: str = ""
    category: str = "general"


@dataclass(frozen=True)
class DataProviderSpec:
    """行情/估值等数据源插件。"""

    id: str
    kind: str  # market | valuation | fund | macro
    fetch: Callable[..., Any] = field(repr=False)
    description: str = ""
