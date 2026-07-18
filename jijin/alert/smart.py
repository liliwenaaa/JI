from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jijin.agents.coach import explain_action
from jijin.alert.position import PositionAdvice, generate_alerts
from jijin.config import load_config
from jijin.engine.scoring import compute_ai_score
from jijin.engine.trend import analyze_trend
from jijin.portfolio.holdings import load_holdings, portfolio_total


@dataclass
class SmartAlert:
    category: str  # 估值 / 趋势 / 风险 / 再平衡 / 定投
    level: str  # info / warn / action
    index: str
    title: str
    message: str
    action: str | None = None
    amount: float | None = None
    current_pct: float | None = None
    target_pct: float | None = None
    delta_pct: float | None = None


def generate_smart_alerts(cfg: dict[str, Any] | None = None, force: bool = False) -> list[SmartAlert]:
    """规划中的多类型提醒：估值、趋势、风险、再平衡、定投。"""
    cfg = cfg or load_config()
    out: list[SmartAlert] = []
    indexes = list(cfg.get("valuation", {}).get("watch_indexes") or [])
    holdings = load_holdings(cfg)
    total = portfolio_total(cfg, holdings)

    # 1) 估值 + 再平衡（复用仓位建议）
    advices: list[PositionAdvice] = generate_alerts(cfg, force=force)
    for a in advices:
        if a.action in {"增持", "减持"}:
            sign = "+" if a.delta_pct > 0 else "−"
            out.append(
                SmartAlert(
                    category="再平衡",
                    level="action",
                    index=a.index,
                    title=f"{a.index} · {a.action}",
                    message=(
                        f"{a.label}，{a.current_pct:.1f}% → {a.target_pct:.1f}% "
                        f"（{sign}{abs(a.delta_pct):.1f}pct，约 ¥{abs(a.suggest_amount):,.0f}）"
                    ),
                    action=a.action,
                    amount=abs(a.suggest_amount),
                    current_pct=a.current_pct,
                    target_pct=a.target_pct,
                    delta_pct=a.delta_pct,
                )
            )
            pct_txt = "—" if a.percentile is None else f"{a.percentile:.0f}%"
            out.append(
                SmartAlert(
                    category="估值",
                    level="warn" if a.label in {"偏高", "高估"} else "info",
                    index=a.index,
                    title=f"{a.index} · {a.label}",
                    message=f"{a.metric.upper()} 分位 {pct_txt}",
                )
            )
        elif a.label in {"低估", "高估"}:
            pct_txt = "—" if a.percentile is None else f"{a.percentile:.0f}%"
            out.append(
                SmartAlert(
                    category="估值",
                    level="info",
                    index=a.index,
                    title=f"{a.index} · {a.label}",
                    message=f"{a.metric.upper()} 分位 {pct_txt}",
                )
            )

    # 2) 趋势 / 风险
    for index in indexes:
        try:
            trend = analyze_trend(index, cfg=cfg, force=force)
            score = compute_ai_score(index, cfg=cfg, force=force)
        except Exception as exc:  # noqa: BLE001
            out.append(
                SmartAlert(
                    category="风险",
                    level="warn",
                    index=index,
                    title=f"{index} 数据异常",
                    message=str(exc),
                )
            )
            continue

        if trend.score >= 70 and trend.ma_signal in {"多头排列", "站上中期均线"}:
            out.append(
                SmartAlert(
                    category="趋势",
                    level="info",
                    index=index,
                    title=f"{index} · 偏多",
                    message=f"趋势分 {trend.score:.0f} · {trend.ma_signal} · 偏多 {trend.probability_up:.0%}",
                )
            )
        if trend.score <= 35 or trend.ma_signal == "空头排列":
            out.append(
                SmartAlert(
                    category="趋势",
                    level="warn",
                    index=index,
                    title=f"{index} · 偏弱",
                    message=f"趋势分 {trend.score:.0f} · {trend.ma_signal} · {trend.macd_signal}",
                )
            )
        if trend.risk_level == "高" or (trend.volatility or 0) > 28:
            out.append(
                SmartAlert(
                    category="风险",
                    level="warn",
                    index=index,
                    title=f"{index} · 高波动",
                    message=f"风险 {trend.risk_level} · 年化波动约 {trend.volatility}%",
                )
            )
        if score.label == "机会":
            out.append(
                SmartAlert(
                    category="估值",
                    level="info",
                    index=index,
                    title=f"{index} · 机会区",
                    message=f"AI 综合分 {score.total:.0f}",
                )
            )

    # 3) 定投提醒（每月固定提示）
    day = datetime.now().day
    dca_day = int((cfg.get("alert") or {}).get("dca_day") or 1)
    monthly = float((cfg.get("alert") or {}).get("monthly_dca") or 3000)
    if day == dca_day or (cfg.get("alert") or {}).get("always_show_dca"):
        out.append(
            SmartAlert(
                category="定投",
                level="action",
                index="组合",
                title="定投提醒",
                message=f"计划月定投约 ¥{monthly:,.0f}",
                action="定投",
                amount=monthly,
            )
        )
    else:
        out.append(
            SmartAlert(
                category="定投",
                level="info",
                index="组合",
                title="定投日历",
                message=f"下次建议：每月 {dca_day} 日 · 总资产约 ¥{total:,.0f}",
            )
        )

    # 去重：同 title 保留一条
    seen: set[str] = set()
    uniq: list[SmartAlert] = []
    for a in out:
        key = f"{a.category}:{a.title}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    return uniq
