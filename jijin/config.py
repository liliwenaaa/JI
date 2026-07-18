from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.yaml"
EXAMPLE_CONFIG = ROOT / "config.example.yaml"


def project_root() -> Path:
    return ROOT


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载配置。若默认 config.yaml 不存在，则从 example 复制后再读，避免写回污染示例文件。"""
    cfg_path = Path(path) if path else Path(os.environ.get("JIJIN_CONFIG", DEFAULT_CONFIG))
    if not cfg_path.exists():
        if cfg_path.resolve() == DEFAULT_CONFIG.resolve() and EXAMPLE_CONFIG.exists():
            shutil.copyfile(EXAMPLE_CONFIG, DEFAULT_CONFIG)
            cfg_path = DEFAULT_CONFIG
        elif EXAMPLE_CONFIG.exists():
            cfg_path = EXAMPLE_CONFIG
        else:
            raise FileNotFoundError(f"配置文件不存在: {cfg_path}")
    with cfg_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["_config_path"] = str(cfg_path.resolve())
    return data


def cache_dir(cfg: dict[str, Any]) -> Path:
    raw = cfg.get("cache", {}).get("dir", "data")
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def to_yaml_safe(obj: Any) -> Any:
    """把 numpy / Path 等转成 PyYAML 可序列化的内建类型。"""
    if isinstance(obj, dict):
        return {str(k): to_yaml_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_yaml_safe(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    # numpy 标量（含 np.float64），避免 RepresenterError
    mod = type(obj).__module__ or ""
    item = getattr(obj, "item", None)
    if callable(item) and mod.startswith("numpy"):
        try:
            return item()
        except Exception:
            return float(obj) if hasattr(obj, "__float__") else str(obj)
    if isinstance(obj, float):
        return float(obj)
    if isinstance(obj, int) and not isinstance(obj, bool):
        return int(obj)
    return obj


def save_config(cfg: dict[str, Any], path: str | Path | None = None) -> Path:
    """写回 YAML；忽略运行时字段 _config_path。"""
    cfg_path = Path(path) if path else Path(cfg.get("_config_path") or DEFAULT_CONFIG)
    # 禁止把运行配置写回 example 模板
    if cfg_path.resolve() == EXAMPLE_CONFIG.resolve():
        cfg_path = DEFAULT_CONFIG
    payload = {k: v for k, v in cfg.items() if not str(k).startswith("_")}
    payload = to_yaml_safe(payload)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            payload,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    return cfg_path.resolve()
