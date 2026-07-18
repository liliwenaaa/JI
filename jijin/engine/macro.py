from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from jijin.config import load_config
from jijin.data.macro import latest_macro_raw
from jijin.engine.settings import get_macro_settings


@dataclass
class MacroSnapshot:
    macro_score: float
    policy_score: float
    stance: str  # 宽松 / 中性 / 偏紧
    label: str
    pmi: float | None = None
    cpi: float | None = None
    m2_yoy: float | None = None
    m1_yoy: float | None = None
    lpr_1y: float | None = None
    lpr_delta: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _score_pmi(pmi: float | None, thresholds: dict[str, float]) -> float:
    if pmi is None:
        return 50.0
    expansion = float(thresholds["pmi_expansion"])
    strong = float(thresholds["pmi_strong"])
    if pmi >= strong:
        return float(np.clip(70 + (pmi - strong) * 8, 70, 95))
    if pmi >= expansion:
        return float(np.clip(55 + (pmi - expansion) * 7.5, 55, 70))
    # 收缩：越低越差，但极端低可能有政策对冲预期，不完全打到地板
    return float(np.clip(50 - (expansion - pmi) * 8, 15, 50))


def _score_cpi(cpi: float | None, thresholds: dict[str, float]) -> float:
    if cpi is None:
        return 50.0
    low = float(thresholds["cpi_low"])
    comfort_high = float(thresholds["cpi_comfort_high"])
    high = float(thresholds["cpi_high"])
    if low <= cpi <= comfort_high:
        return 78.0
    if cpi < low:
        # 通缩压力
        return float(np.clip(55 - (low - cpi) * 12, 25, 55))
    if cpi <= high:
        return float(np.clip(70 - (cpi - comfort_high) * 10, 40, 70))
    return float(np.clip(35 - (cpi - high) * 5, 10, 35))


def _score_liquidity(m2: float | None, thresholds: dict[str, float]) -> float:
    if m2 is None:
        return 50.0
    soft = float(thresholds["m2_soft"])
    comfort = float(thresholds["m2_comfort"])
    hot = float(thresholds["m2_hot"])
    if soft <= m2 <= comfort:
        return 72.0
    if m2 < soft:
        return float(np.clip(55 - (soft - m2) * 4, 25, 55))
    if m2 <= hot:
        return float(np.clip(70 - (m2 - comfort) * 3, 45, 70))
    # 过热流动性对风险资产短期利好但中期风险上升
    return float(np.clip(55 - (m2 - hot) * 2, 30, 55))


def _infer_stance(
    lpr_delta: float | None,
    m2: float | None,
    thresholds: dict[str, float],
) -> str:
    score = 0
    if lpr_delta is not None:
        if lpr_delta < -1e-9:
            score += 2
        elif lpr_delta > 1e-9:
            score -= 2
    if m2 is not None:
        if m2 >= float(thresholds["m2_comfort"]):
            score += 1
        elif m2 < float(thresholds["m2_soft"]):
            score -= 1
    if score >= 2:
        return "宽松"
    if score <= -2:
        return "偏紧"
    return "中性"


def _stance_score(stance: str) -> float:
    return {"宽松": 78.0, "中性": 55.0, "偏紧": 32.0}.get(stance, 50.0)


def evaluate_macro(
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    raw: dict[str, Any] | None = None,
) -> MacroSnapshot:
    cfg = cfg or load_config()
    settings = get_macro_settings(cfg)
    thresholds = settings["thresholds"]
    weights = settings["weights"]
    policy_cfg = settings["policy"]

    raw = raw if raw is not None else latest_macro_raw(cfg, force=force)
    pmi = raw.get("pmi")
    cpi = raw.get("cpi")
    m2 = raw.get("m2_yoy")
    m1 = raw.get("m1_yoy")
    lpr = raw.get("lpr_1y")
    lpr_prev = raw.get("lpr_1y_prev")
    lpr_delta = None
    if lpr is not None and lpr_prev is not None:
        lpr_delta = float(lpr) - float(lpr_prev)

    pmi_s = _score_pmi(None if pmi is None else float(pmi), thresholds)
    cpi_s = _score_cpi(None if cpi is None else float(cpi), thresholds)
    liq_s = _score_liquidity(None if m2 is None else float(m2), thresholds)

    macro_score = float(
        np.clip(
            weights["pmi"] * pmi_s + weights["cpi"] * cpi_s + weights["liquidity"] * liq_s,
            0,
            100,
        )
    )

    manual_stance = str(policy_cfg.get("stance") or "auto").lower()
    stance_map = {
        "easing": "宽松",
        "宽松": "宽松",
        "neutral": "中性",
        "中性": "中性",
        "tightening": "偏紧",
        "偏紧": "偏紧",
        "auto": "auto",
        "自动": "auto",
    }
    resolved = stance_map.get(manual_stance, "auto")
    if resolved == "auto":
        stance = _infer_stance(lpr_delta, None if m2 is None else float(m2), thresholds)
    else:
        stance = resolved

    if policy_cfg.get("manual_score") is not None:
        policy_score = float(np.clip(float(policy_cfg["manual_score"]), 0, 100))
    else:
        policy_score = _stance_score(stance)
        # LPR 下调额外加分，上调减分
        if lpr_delta is not None:
            if lpr_delta < 0:
                policy_score = float(np.clip(policy_score + min(12.0, abs(lpr_delta) * 40), 0, 95))
            elif lpr_delta > 0:
                policy_score = float(np.clip(policy_score - min(12.0, abs(lpr_delta) * 40), 5, 100))

    if macro_score >= 65 and policy_score >= 60:
        label = "宏观友好"
    elif macro_score <= 40 or policy_score <= 35:
        label = "宏观承压"
    else:
        label = "宏观中性"

    return MacroSnapshot(
        macro_score=round(macro_score, 1),
        policy_score=round(policy_score, 1),
        stance=stance,
        label=label,
        pmi=None if pmi is None else round(float(pmi), 1),
        cpi=None if cpi is None else round(float(cpi), 2),
        m2_yoy=None if m2 is None else round(float(m2), 2),
        m1_yoy=None if m1 is None else round(float(m1), 2),
        lpr_1y=None if lpr is None else round(float(lpr), 2),
        lpr_delta=None if lpr_delta is None else round(float(lpr_delta), 2),
        details={
            "component_scores": {
                "pmi": round(pmi_s, 1),
                "cpi": round(cpi_s, 1),
                "liquidity": round(liq_s, 1),
            },
            "weights": weights,
            "raw": {
                "pmi_date": raw.get("pmi_date"),
                "cpi_date": raw.get("cpi_date"),
                "money_month": raw.get("money_month"),
                "lpr_date": raw.get("lpr_date"),
                "errors": raw.get("errors") or [],
            },
            "policy_mode": manual_stance,
        },
    )
