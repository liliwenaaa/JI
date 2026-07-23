"""内置提醒插件。"""
from __future__ import annotations

from jijin.alert.position import generate_alerts
from jijin.alert.smart import generate_smart_alerts
from jijin.plugin.base import AlertSpec
from jijin.plugin.registry import PluginRegistry


def register(reg: PluginRegistry) -> None:
    reg.register_alert(
        AlertSpec(
            id="position",
            run=generate_alerts,
            description="仓位/估值再平衡建议",
            category="position",
        ),
        replace=True,
    )
    reg.register_alert(
        AlertSpec(
            id="smart",
            run=generate_smart_alerts,
            description="智能综合提醒",
            category="smart",
        ),
        replace=True,
    )
