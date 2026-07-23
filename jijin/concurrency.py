from __future__ import annotations

from typing import Any


def configured_workers(cfg: dict[str, Any] | None, task_count: int) -> int:
    """公开数据接口并发数：默认 8，上限 12（I/O 密集，多线程能明显缩短墙钟时间）。"""
    configured = int(((cfg or {}).get("performance") or {}).get("max_workers") or 8)
    return max(1, min(configured, 12, max(1, int(task_count))))
