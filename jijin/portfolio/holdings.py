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


def holdings_to_records(holdings: list[Holding] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in holdings:
        if isinstance(h, Holding):
            rows.append(
                {
                    "code": h.code,
                    "name": h.name,
                    "amount": float(h.amount),
                    "index": h.index,
                    "enabled": bool(h.enabled),
                }
            )
        else:
            rows.append(
                {
                    "code": str(h.get("code", "")).zfill(6) if h.get("code") else "",
                    "name": str(h.get("name") or ""),
                    "amount": float(h.get("amount") or 0),
                    "index": str(h.get("index") or ""),
                    "enabled": bool(h.get("enabled", True)),
                }
            )
    return rows


def apply_strategy_to_holdings(
    *,
    total_assets: float,
    sleeves: list[Any],
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """把策略目标仓位同步为真实持仓金额。

    - 覆盖策略中出现的跟踪指数对应持仓；
    - 保留未出现在策略里的其他持仓；
    - 仅写入有推荐基金代码的 sleeve。
    """
    existing = list(existing or [])
    covered = {str(getattr(s, "index", "") or "") for s in sleeves}
    covered.discard("")
    kept = [h for h in existing if str(h.get("index") or "") not in covered]
    synced: list[dict[str, Any]] = []
    for s in sleeves:
        index = str(getattr(s, "index", "") or "")
        code = str(getattr(s, "fund_code", "") or "").strip()
        if not index or not code:
            continue
        weight = float(getattr(s, "target_weight", 0) or 0)
        amount = max(0.0, float(total_assets) * weight / 100.0)
        synced.append(
            {
                "code": code.zfill(6),
                "name": str(getattr(s, "fund_name", "") or ""),
                "amount": round(amount, 2),
                "index": index,
                "enabled": True,
            }
        )
    return kept + synced
