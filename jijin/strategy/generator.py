from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from jijin.alert.position import map_percentile_to_band
from jijin.config import load_config
from jijin.data.valuation import fetch_index_valuation
from jijin.screener.index_fund import screen_index_funds


@dataclass
class StrategySleeve:
    index: str
    base_weight: float
    target_weight: float
    valuation_label: str
    pe_percentile: float | None
    fund_code: str | None = None
    fund_name: str | None = None
    fund_score: float | None = None
    monthly_amount: float = 0.0
    note: str = ""


@dataclass
class StrategyPlan:
    name: str
    profile: str
    risk: str
    total_assets: float
    monthly_dca: float
    equity_ratio: float
    cash_bond_ratio: float
    sleeves: list[StrategySleeve] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for s in self.sleeves:
            rows.append(
                {
                    "指数": s.index,
                    "基准仓位%": round(s.base_weight, 1),
                    "目标仓位%": round(s.target_weight, 1),
                    "估值": s.valuation_label,
                    "PE百分位": None if s.pe_percentile is None else round(s.pe_percentile, 1),
                    "推荐代码": s.fund_code or "-",
                    "推荐基金": s.fund_name or "-",
                    "综合分": s.fund_score,
                    "月定投(元)": round(s.monthly_amount, 0),
                    "说明": s.note,
                }
            )
        return pd.DataFrame(rows)

    def to_markdown(self) -> str:
        lines = [
            f"# {self.name}",
            "",
            f"- 风险偏好：{self.risk}",
            f"- 策略模板：{self.profile}",
            f"- 总资产：{self.total_assets:,.0f} 元",
            f"- 月定投：{self.monthly_dca:,.0f} 元",
            f"- 权益目标仓位：{self.equity_ratio:.1f}%　｜　现金/债券缓冲：{self.cash_bond_ratio:.1f}%",
            "",
            self.summary,
            "",
            "## 配置明细",
            "",
            "| 指数 | 基准% | 目标% | 估值 | PE百分位 | 基金 | 月定投 |",
            "|---|---:|---:|---|---:|---|---:|",
        ]
        for s in self.sleeves:
            pct = "-" if s.pe_percentile is None else f"{s.pe_percentile:.1f}"
            fund = f"{s.fund_code or '-'} {s.fund_name or ''}".strip()
            lines.append(
                f"| {s.index} | {s.base_weight:.1f} | {s.target_weight:.1f} | "
                f"{s.valuation_label} | {pct} | {fund} | {s.monthly_amount:,.0f} |"
            )
        lines.extend(["", "## 执行规则", ""])
        for r in self.rules:
            lines.append(f"- {r}")
        lines.extend(
            [
                "",
                "> 本策略由程序根据公开估值与筛选规则生成，仅供学习参考，不构成投资建议。",
            ]
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 风险偏好 → 基准权益仓位与指数权重模板
RISK_PROFILES: dict[str, dict[str, Any]] = {
    "稳健": {
        "equity_base": 40,
        "indexes": {"沪深300": 50, "中证500": 20, "中证红利": 30},
        "desc": "偏大盘与红利，回撤更克制",
    },
    "均衡": {
        "equity_base": 60,
        "indexes": {"沪深300": 40, "中证500": 30, "中证1000": 20, "创业板50": 10},
        "desc": "大小盘搭配，适合长期定投",
    },
    "积极": {
        "equity_base": 80,
        "indexes": {"沪深300": 25, "中证500": 25, "中证1000": 25, "创业板50": 25},
        "desc": "提高中小盘与成长暴露",
    },
}

STRATEGY_TEMPLATES: dict[str, dict[str, Any]] = {
    "valuation_dynamic": {
        "label": "估值动态再平衡",
        "desc": "按各指数 PE 百分位缩放计划仓位，低估多买、高估少买",
    },
    "core_satellite": {
        "label": "核心宽基 + 卫星",
        "desc": "沪深300/中证500 作核心，中证1000/创业板作卫星",
        "indexes": {"沪深300": 45, "中证500": 25, "中证1000": 15, "创业板50": 15},
    },
    "dividend_defense": {
        "label": "红利防御",
        "desc": "高配红利与大盘，适合偏高估值环境",
        "indexes": {"沪深300": 40, "中证红利": 40, "中证500": 20},
        "force_equity_cap": 50,
    },
    "growth_barbell": {
        "label": "哑铃成长",
        "desc": "大盘价值 + 成长成长两端配置",
        "indexes": {"沪深300": 40, "创业板50": 35, "中证1000": 25},
    },
}


def _valuation_multiplier(percentile: float | None, bands: list[dict[str, Any]]) -> tuple[str, float]:
    if percentile is None or not bands:
        return "未知", 1.0
    band = map_percentile_to_band(float(percentile), bands)
    label = str(band.get("label") or "")
    # 以适中 50 为 1.0
    ref = 50.0
    for b in bands:
        if str(b.get("label") or "") in {"适中", "正常", "中性"}:
            ref = float(b.get("target_pct") or 50)
            break
    if "weight_mult" in band:
        return label, float(band["weight_mult"])
    return label, float(band.get("target_pct", ref)) / ref


def _pick_fund_for_index(index: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    scfg = dict(cfg)
    scfg["screen"] = {
        "index_keywords": [index.replace("指", "")],
        "share_class": "A",
        "min_scale_yi": 2.0,
        "max_purchase_fee": 0.2,
        "subtype_mode": "passive",
        "exclude_keywords": ["QDII"],
        "sort_by": "score_desc",
        "top_n": 5,
        "rule_4433": False,
        "enrich_fees": False,
    }
    # 红利指数名称兼容
    if "红利" in index:
        scfg["screen"]["index_keywords"] = ["红利"]
        scfg["screen"]["subtype_mode"] = "all"
    try:
        df = screen_index_funds(scfg, force=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    row = df.iloc[0]
    return {
        "code": str(row.get("code")),
        "name": str(row.get("name")),
        "score": float(row["score"]) if pd.notna(row.get("score")) else None,
    }


def generate_strategy(
    *,
    risk: str = "均衡",
    template: str = "valuation_dynamic",
    total_assets: float | None = None,
    monthly_dca: float = 3000.0,
    cfg: dict[str, Any] | None = None,
    pick_funds: bool = True,
) -> StrategyPlan:
    cfg = cfg or load_config()
    risk_cfg = RISK_PROFILES.get(risk) or RISK_PROFILES["均衡"]
    tpl = STRATEGY_TEMPLATES.get(template) or STRATEGY_TEMPLATES["valuation_dynamic"]

    total = float(
        total_assets
        if total_assets is not None
        else (cfg.get("portfolio", {}) or {}).get("total_assets")
        or 100000
    )
    equity_base = float(risk_cfg["equity_base"])
    if tpl.get("force_equity_cap") is not None:
        equity_base = min(equity_base, float(tpl["force_equity_cap"]))

    index_weights: dict[str, float] = dict(tpl.get("indexes") or risk_cfg["indexes"])
    # 归一化到 100
    weight_sum = sum(index_weights.values()) or 1.0
    index_weights = {k: v / weight_sum * 100 for k, v in index_weights.items()}

    bands = (cfg.get("valuation") or {}).get("bands") or []
    sleeves: list[StrategySleeve] = []
    target_equity = 0.0

    for index, rel_w in index_weights.items():
        base_w = equity_base * rel_w / 100.0
        label, mult = "未知", 1.0
        pe_pct = None
        try:
            val = fetch_index_valuation(index if index != "中证红利" else "上证红利", cfg=cfg)
            # 中证红利可能不在乐咕列表，尝试上证红利/失败则跳过缩放
            pe_pct = val.pe_percentile
            label, mult = _valuation_multiplier(pe_pct, bands)
        except Exception:
            try:
                # 创业板指别名
                alt = {"创业板指": "创业板50", "中证红利": "上证红利"}.get(index, index)
                val = fetch_index_valuation(alt, cfg=cfg)
                pe_pct = val.pe_percentile
                label, mult = _valuation_multiplier(pe_pct, bands)
            except Exception:
                label, mult = "未知", 1.0

        target_w = max(0.0, base_w * mult)
        target_equity += target_w

        fund = _pick_fund_for_index(index, cfg) if pick_funds else None
        note = f"基准 {base_w:.1f}% × 估值系数 {mult:.2f}"
        sleeve = StrategySleeve(
            index=index,
            base_weight=base_w,
            target_weight=target_w,
            valuation_label=label,
            pe_percentile=pe_pct,
            fund_code=(fund or {}).get("code"),
            fund_name=(fund or {}).get("name"),
            fund_score=(fund or {}).get("score"),
            monthly_amount=0.0,
            note=note,
        )
        sleeves.append(sleeve)

    # 若总权益超过 95%，等比例压缩
    if target_equity > 95:
        scale = 95 / target_equity
        for s in sleeves:
            s.target_weight *= scale
        target_equity = 95.0

    # 月定投按目标仓位比例分配（仅对目标>0）
    pos = [s for s in sleeves if s.target_weight > 0]
    tw = sum(s.target_weight for s in pos) or 1.0
    for s in sleeves:
        s.monthly_amount = monthly_dca * (s.target_weight / tw) if s.target_weight > 0 else 0.0

    cash = max(0.0, 100.0 - target_equity)
    rules = [
        "每月固定日定投；估值偏低月份可把当月额度上浮 20%~50%。",
        "单指数仓位偏离目标超过 5 个百分点时再平衡。",
        "优先选低费率、规模≥2亿的 A 类被动/联接产品。",
        "极端高估（PE百分位>80%）暂停加仓，定投转入货币/短债。",
        "本策略不构成投资建议，请结合自身风险承受能力执行。",
    ]
    summary = (
        f"「{tpl['label']}」×「{risk}」：{risk_cfg['desc']}。"
        f"当前建议权益仓位约 {target_equity:.1f}%（现金/债 {cash:.1f}%），"
        f"月定投 {monthly_dca:,.0f} 元按目标权重拆分到各指数。"
    )

    return StrategyPlan(
        name=f"{tpl['label']}（{risk}）",
        profile=template,
        risk=risk,
        total_assets=total,
        monthly_dca=monthly_dca,
        equity_ratio=target_equity,
        cash_bond_ratio=cash,
        sleeves=sleeves,
        rules=rules,
        summary=summary,
    )
