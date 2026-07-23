"""内置 Agent 插件。"""
from __future__ import annotations

from jijin.agents import (
    build_dashboard,
    calibrate_agent,
    coach_agent,
    macro_agent,
    opportunity_agent,
    portfolio_agent,
    score_agent,
    trend_agent,
    trend_horizons_agent,
    valuation_agent,
)
from jijin.plugin.base import AgentSpec
from jijin.plugin.registry import PluginRegistry


def register(reg: PluginRegistry) -> None:
    specs = [
        AgentSpec("valuation", valuation_agent, "指数估值"),
        AgentSpec("trend", trend_agent, "单周期趋势"),
        AgentSpec("trend_horizons", trend_horizons_agent, "多周期趋势"),
        AgentSpec("score", score_agent, "AI 综合评分"),
        AgentSpec("macro", macro_agent, "宏观环境"),
        AgentSpec("portfolio", portfolio_agent, "智能仓位方案"),
        AgentSpec("coach", coach_agent, "解释说明"),
        AgentSpec("opportunity", opportunity_agent, "重点机会扫描"),
        AgentSpec("calibrate", calibrate_agent, "策略校准"),
        AgentSpec("dashboard", build_dashboard, "决策看板快照", tags=("orchestrator",)),
    ]
    for spec in specs:
        reg.register_agent(spec, replace=True)
