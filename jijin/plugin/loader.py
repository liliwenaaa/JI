"""插件发现与加载。"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Iterable

from jijin.plugin.registry import PluginRegistry, registry

logger = logging.getLogger(__name__)

_BUILTIN_MODULES = (
    "jijin.plugins_builtin.agents",
    "jijin.plugins_builtin.strategies",
    "jijin.plugins_builtin.alerts",
    "jijin.plugins_builtin.data_providers",
    "jijin.plugins_builtin.pages",
)


def _call_register(module_name: str, reg: PluginRegistry) -> None:
    mod = importlib.import_module(module_name)
    register = getattr(mod, "register", None)
    if callable(register):
        register(reg)
        return
    logger.debug("plugin module has no register(): %s", module_name)


def discover_entry_points(group: str = "jijin.plugins") -> list[str]:
    """读取 setuptools / importlib.metadata 入口点。"""
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return []
    eps = entry_points()
    selected = []
    try:
        selected = list(eps.select(group=group))  # type: ignore[attr-defined]
    except Exception:
        selected = list(eps.get(group, []))  # type: ignore[arg-type]
    names: list[str] = []
    for ep in selected:
        try:
            loaded = ep.load()
            if callable(loaded):
                loaded(registry)
            names.append(getattr(ep, "name", str(ep)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("加载入口点插件失败 %s: %s", ep, exc)
    return names


def plugin_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return dict((cfg or {}).get("plugins") or {})


def enabled_page_ids(cfg: dict[str, Any] | None, reg: PluginRegistry | None = None) -> list[str] | None:
    """返回启用的页面 id 列表；None 表示全部启用。"""
    reg = reg or registry
    pc = plugin_config(cfg)
    disabled = set(pc.get("disabled") or [])
    enabled = pc.get("enabled")
    ids = list(reg.pages.keys())
    if enabled is not None:
        want = [str(i) for i in enabled]
        ids = [i for i in want if i in reg.pages]
    return [i for i in ids if i not in disabled]


def load_plugins(
    cfg: dict[str, Any] | None = None,
    *,
    reg: PluginRegistry | None = None,
    reload: bool = False,
    extra_modules: Iterable[str] | None = None,
) -> PluginRegistry:
    """加载内置 + 配置指定 + entry_points 插件。"""
    reg = reg or registry
    if reg._loaded and not reload:
        return reg
    if reload:
        reg.clear()

    modules = list(_BUILTIN_MODULES)
    pc = plugin_config(cfg)
    modules.extend(str(m) for m in (pc.get("modules") or []))
    if extra_modules:
        modules.extend(extra_modules)

    seen: set[str] = set()
    for name in modules:
        if name in seen:
            continue
        seen.add(name)
        try:
            _call_register(name, reg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("加载插件模块失败 %s: %s", name, exc)

    if pc.get("entry_points", True):
        discover_entry_points(str(pc.get("entry_point_group") or "jijin.plugins"))

    reg._loaded = True
    return reg
