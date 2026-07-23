"""示例：自定义页面插件。

在 config.yaml 中启用::

    plugins:
      modules:
        - examples.hello_page_plugin

或通过 entry_points 组 ``jijin.plugins`` 注册。
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from jijin.plugin.base import PageSpec
from jijin.plugin.registry import PluginRegistry


def _render(cfg: dict[str, Any]) -> None:
    _ = cfg
    st.title("Hello Plugin")
    st.write("这是一个示例页面插件，证明扩展点可用。")


def register(reg: PluginRegistry) -> None:
    reg.register_page(
        PageSpec(
            id="hello",
            title="示例插件",
            render=_render,
            order=200,
            description="示例扩展页面",
        ),
        replace=True,
    )
