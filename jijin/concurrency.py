from __future__ import annotations

from typing import Any


def configured_workers(cfg: dict[str, Any] | None, task_count: int) -> int:
    """Return a bounded worker count suitable for public data APIs."""
    configured = int(((cfg or {}).get("performance") or {}).get("max_workers") or 5)
    return max(1, min(configured, 8, max(1, int(task_count))))
