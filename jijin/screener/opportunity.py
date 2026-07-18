from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from jijin.concurrency import configured_workers
from jijin.config import load_config
from jijin.data.market import index_group_of, list_index_names
from jijin.engine.settings import get_trend_settings
from jijin.engine.trend import TrendResult, analyze_trend


@dataclass
class IndexOpportunity:
    """市场指数机会：按策略参数下的上涨方向置信度排序。"""

    rank: int
    index: str
    probability_up: float
    bias: str
    trend_score: float
    horizon: str
    horizon_label: str
    horizon_days: int
    risk_level: str
    move_band_pct: float | None = None
    ai_score: float | None = None
    ai_label: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def market_index_universe(
    cfg: dict[str, Any] | None = None,
    group: str | None = None,
) -> list[str]:
    """可分析的市场指数宇宙（宽基 + 行业/主题），不是基金产品。"""
    custom = None
    if cfg:
        custom = (cfg.get("opportunity") or {}).get("universe_group")
    return list_index_names(group=group or custom)


def scan_index_opportunities(
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    top_n: int | None = None,
    horizon: str | None = None,
) -> list[IndexOpportunity]:
    """扫描全部市场指数，按默认展望周期的偏多概率排出前 N。

    决策口径完全来自策略参数：
    - `trend.default_horizon`（或传入 horizon）决定展望周期与指标窗口；
    - 趋势/评分阈值与权重来自 config 的 trend / scoring 节。
    不使用基金筛选条件。
    """
    cfg = cfg or load_config()
    trend_cfg = get_trend_settings(cfg)
    horizon_key = horizon or str(trend_cfg.get("default_horizon") or "1m")
    limit = int(top_n if top_n is not None else (cfg.get("opportunity") or {}).get("top_n") or 10)
    limit = max(1, min(limit, 50))

    universe = market_index_universe(cfg)
    workers = configured_workers(cfg, len(universe))
    candidates: list[TrendResult] = []
    errors: list[str] = []

    def scan_one(name: str) -> TrendResult:
        trend = analyze_trend(name, cfg=cfg, force=force, horizon=horizon_key)
        if trend.details.get("error"):
            raise RuntimeError(str(trend.details["error"]))
        return trend

    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="index-scan",
    ) as executor:
        futures = {executor.submit(scan_one, name): name for name in universe}
        for future in as_completed(futures):
            name = futures[future]
            try:
                candidates.append(future.result())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {exc}")

    candidates.sort(
        key=lambda t: (float(t.probability_up), float(t.score)),
        reverse=True,
    )

    out: list[IndexOpportunity] = []
    for rank, trend in enumerate(candidates[:limit], start=1):
        details = {
            "regime": (trend.details or {}).get("regime"),
            "supertrend_dir": (trend.details or {}).get("supertrend_dir"),
            "strength": trend.strength,
            "group": index_group_of(trend.index),
        }
        if rank == 1 and errors:
            details["scan_errors"] = errors
        out.append(
            IndexOpportunity(
                rank=rank,
                index=trend.index,
                probability_up=float(trend.probability_up),
                bias=trend.bias,
                trend_score=float(trend.score),
                horizon=trend.horizon,
                horizon_label=trend.horizon_label,
                horizon_days=int(trend.horizon_days),
                risk_level=trend.risk_level,
                move_band_pct=trend.move_band_pct,
                details=details,
            )
        )
    if not out and errors:
        # 保证 UI 仍能读到错误列表
        out.append(
            IndexOpportunity(
                rank=0,
                index="—",
                probability_up=0.5,
                bias="中性",
                trend_score=50.0,
                horizon=horizon_key,
                horizon_label="",
                horizon_days=0,
                risk_level="中",
                details={"scan_errors": errors, "empty": True},
            )
        )
    return out


def opportunity_scan_errors(items: list[IndexOpportunity]) -> list[str]:
    for item in items:
        errs = (item.details or {}).get("scan_errors")
        if errs:
            return list(errs)
    return []


def opportunities_to_rows(items: list[IndexOpportunity]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        if (item.details or {}).get("empty"):
            continue
        st = (item.details or {}).get("supertrend_dir")
        st_label = "—"
        if st is not None:
            st_label = "多" if int(st) >= 1 else "空"
        rows.append(
            {
                "排名": item.rank,
                "指数": item.index,
                "上涨概率": item.probability_up,
                "方向": item.bias,
                "趋势分": item.trend_score,
                "体制": (item.details or {}).get("regime") or "—",
                "分组": (item.details or {}).get("group") or index_group_of(item.index),
                "Supertrend": st_label,
                "展望": item.horizon_label,
                "风险": item.risk_level,
                "波动带宽%": item.move_band_pct,
            }
        )
    return rows
