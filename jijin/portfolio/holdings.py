from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jijin.config import load_config


@dataclass
class Holding:
    code: str
    name: str
    amount: float
    index: str
    enabled: bool = True


def load_holdings(cfg: dict[str, Any] | None = None) -> list[Holding]:
    cfg = cfg or load_config()
    rows = cfg.get("portfolio", {}).get("holdings") or []
    out: list[Holding] = []
    for r in rows:
        enabled = r.get("enabled", True)
        if enabled is False:
            continue
        out.append(
            Holding(
                code=str(r.get("code", "")).zfill(6),
                name=str(r.get("name") or ""),
                amount=float(r.get("amount") or 0),
                index=str(r.get("index") or ""),
                enabled=True,
            )
        )
    return out


def portfolio_total(cfg: dict[str, Any] | None = None, holdings: list[Holding] | None = None) -> float:
    cfg = cfg or load_config()
    holdings = holdings if holdings is not None else load_holdings(cfg)
    configured = cfg.get("portfolio", {}).get("total_assets")
    if configured is not None:
        return float(configured)
    return float(sum(h.amount for h in holdings))


def exposure_by_index(holdings: list[Holding], total: float) -> dict[str, dict[str, float]]:
    """按跟踪指数汇总金额与仓位占比。"""
    buckets: dict[str, float] = {}
    for h in holdings:
        key = h.index or "未分类"
        buckets[key] = buckets.get(key, 0.0) + h.amount
    denom = total if total > 0 else 1.0
    return {
        k: {"amount": v, "weight_pct": v / denom * 100}
        for k, v in buckets.items()
    }
