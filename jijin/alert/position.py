from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from jijin.config import load_config
from jijin.data.valuation import IndexValuation, fetch_index_valuation, fetch_watch_valuations
from jijin.portfolio.holdings import exposure_by_index, load_holdings, portfolio_total


@dataclass
class PositionAdvice:
    index: str
    label: str
    percentile: float | None
    metric: str
    metric_value: float | None
    current_pct: float
    target_pct: float
    delta_pct: float
    action: str
    suggest_amount: float
    message: str


def map_percentile_to_band(percentile: float, bands: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(bands, key=lambda b: float(b["max_percentile"]))
    for band in ordered:
        if percentile <= float(band["max_percentile"]):
            return band
    return ordered[-1]


def map_percentile_to_target(percentile: float, bands: list[dict[str, Any]]) -> tuple[str, float]:
    """兼容旧接口：返回 (label, target_pct)。优先读 weight_mult。"""
    band = map_percentile_to_band(percentile, bands)
    label = str(band.get("label") or "")
    if "target_pct" in band:
        return label, float(band["target_pct"])
    # weight_mult 相对适中=1.0，换算到 0~100 的示意仓位
    mult = float(band.get("weight_mult", 1.0))
    return label, round(50.0 * mult, 2)


def _reference_target(bands: list[dict[str, Any]]) -> float:
    """适中档的参考目标（默认 50），用于把 target_pct 换算成权重乘数。"""
    for band in bands:
        if str(band.get("label") or "") in {"适中", "正常", "中性"}:
            if "target_pct" in band:
                return float(band["target_pct"])
            return 50.0 * float(band.get("weight_mult", 1.0))
    return 50.0


def _action_from_delta(delta: float, min_rebalance: float) -> str:
    if abs(delta) < min_rebalance:
        return "维持"
    return "增持" if delta > 0 else "减持"


def _planned_pct(index: str, current_pct: float, cfg: dict[str, Any]) -> float | None:
    """计划仓位：config portfolio.index_plans > 当前持仓；皆无则 None（仅观察）。"""
    plans = cfg.get("portfolio", {}).get("index_plans") or {}
    if index in plans:
        return float(plans[index])
    # 模糊匹配计划键
    for k, v in plans.items():
        if k in index or index in k:
            return float(v)
    if current_pct > 0:
        return current_pct
    return None


def build_advice_for_index(
    index: str,
    current_pct: float,
    valuation: IndexValuation,
    cfg: dict[str, Any],
    total_assets: float,
) -> PositionAdvice:
    vcfg = cfg.get("valuation", {})
    metric = (vcfg.get("metric") or "pe").lower()
    bands = vcfg.get("bands") or []
    min_reb = float(cfg.get("alert", {}).get("min_rebalance_pct", 5))

    if metric == "pb":
        pct = valuation.pb_percentile
        value = valuation.pb
    else:
        pct = valuation.pe_percentile
        value = valuation.pe
        metric = "pe"

    if pct is None or not bands:
        return PositionAdvice(
            index=index,
            label="未知",
            percentile=pct,
            metric=metric,
            metric_value=value,
            current_pct=current_pct,
            target_pct=current_pct,
            delta_pct=0.0,
            action="无法判断",
            suggest_amount=0.0,
            message=f"{index}: 估值数据不足，跳过提醒",
        )

    band = map_percentile_to_band(float(pct), bands)
    label = str(band.get("label") or "")
    planned = _planned_pct(index, current_pct, cfg)

    # 无计划且无持仓：只观察，不给整仓加减建议
    if planned is None:
        return PositionAdvice(
            index=index,
            label=label,
            percentile=float(pct),
            metric=metric,
            metric_value=value,
            current_pct=0.0,
            target_pct=0.0,
            delta_pct=0.0,
            action="观察",
            suggest_amount=0.0,
            message=(
                f"{index}: {label}（{metric.upper()}百分位 {pct:.1f}%），"
                f"当前无持仓/未配置计划仓位，仅观察"
            ),
        )

    ref = _reference_target(bands)
    if "weight_mult" in band:
        mult = float(band["weight_mult"])
    else:
        mult = float(band["target_pct"]) / ref if ref else 1.0
    target = max(0.0, planned * mult)
    delta = target - current_pct
    action = _action_from_delta(delta, min_reb)
    amount = total_assets * delta / 100.0

    if action == "维持":
        msg = (
            f"{index}: {label}（{metric.upper()}百分位 {pct:.1f}%），"
            f"当前仓位 {current_pct:.1f}% ≈ 目标 {target:.1f}% "
            f"（计划 {planned:.1f}% × {mult:.2f}），建议维持"
        )
    else:
        msg = (
            f"{index}: {label}（{metric.upper()}百分位 {pct:.1f}%），"
            f"当前 {current_pct:.1f}% → 目标 {target:.1f}% "
            f"（计划 {planned:.1f}% × {mult:.2f}），"
            f"建议{action} {abs(delta):.1f} 个百分点"
            f"（约 {abs(amount):,.0f} 元）"
        )
    return PositionAdvice(
        index=index,
        label=label,
        percentile=float(pct),
        metric=metric,
        metric_value=value,
        current_pct=current_pct,
        target_pct=target,
        delta_pct=delta,
        action=action,
        suggest_amount=amount,
        message=msg,
    )


def generate_alerts(cfg: dict[str, Any] | None = None, force: bool = False) -> list[PositionAdvice]:
    cfg = cfg or load_config()
    holdings = load_holdings(cfg)
    total = portfolio_total(cfg, holdings)
    exposure = exposure_by_index(holdings, total)

    indexes = set(exposure.keys())
    for name in cfg.get("valuation", {}).get("watch_indexes") or []:
        indexes.add(name)
    for name in (cfg.get("portfolio", {}).get("index_plans") or {}):
        indexes.add(name)

    advices: list[PositionAdvice] = []
    for index in sorted(indexes):
        if index == "未分类":
            continue
        current = exposure.get(index, {}).get("weight_pct", 0.0)
        try:
            val = fetch_index_valuation(index, cfg=cfg, force=force)
        except Exception as exc:  # noqa: BLE001
            advices.append(
                PositionAdvice(
                    index=index,
                    label="错误",
                    percentile=None,
                    metric=cfg.get("valuation", {}).get("metric", "pe"),
                    metric_value=None,
                    current_pct=current,
                    target_pct=current,
                    delta_pct=0.0,
                    action="无法判断",
                    suggest_amount=0.0,
                    message=f"{index}: 获取估值失败 — {exc}",
                )
            )
            continue
        advices.append(build_advice_for_index(index, current, val, cfg, total))
    return advices


def notify(messages: list[str], mode: str = "console") -> None:
    if mode in {"console", "both"}:
        print("\n".join(messages))
    if mode in {"desktop", "both"}:
        if shutil.which("notify-send"):
            summary = "JiJin 加减仓提醒"
            body = "；".join(messages)[:200]
            subprocess.run(["notify-send", summary, body], check=False)
        else:
            print("[notify] 系统无 notify-send，已回退到控制台输出")


def run_alert(cfg: dict[str, Any] | None = None, force: bool = False) -> list[PositionAdvice]:
    cfg = cfg or load_config()
    advices = generate_alerts(cfg, force=force)
    mode = cfg.get("alert", {}).get("notify", "console")
    action_msgs = [a.message for a in advices if a.action in {"增持", "减持"}]
    if action_msgs and mode in {"desktop", "both"}:
        notify(action_msgs, mode="desktop")
    return advices


def valuation_snapshot(cfg: dict[str, Any] | None = None, force: bool = False) -> list[IndexValuation]:
    return fetch_watch_valuations(cfg or load_config(), force=force)
