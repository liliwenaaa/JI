from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jijin.engine.scoring import ScoreBreakdown
from jijin.engine.trend import TrendResult


@dataclass
class Explanation:
    title: str
    why_recommend: list[str] = field(default_factory=list)
    why_not: list[str] = field(default_factory=list)
    risk_sources: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    summary: str = ""


def explain_score(score: ScoreBreakdown, trend: TrendResult | None = None) -> Explanation:
    why: list[str] = []
    why_not: list[str] = []
    risks: list[str] = []
    evidence: list[str] = []

    pe_pct = score.components.get("pe_percentile")
    if pe_pct is not None:
        evidence.append(f"PE 历史百分位约 {pe_pct:.1f}%（估值维度得分 {score.valuation:.0f}）")
        if pe_pct < 30:
            why.append(f"估值处于历史偏低区间（PE百分位 {pe_pct:.1f}%），长期定投性价比更好。")
        elif pe_pct > 70:
            why_not.append(f"估值偏高（PE百分位 {pe_pct:.1f}%），追高性价比一般。")

    if score.trend >= 65:
        why.append(f"趋势评分 {score.trend:.0f}，技术面偏多。")
    elif score.trend <= 40:
        why_not.append(f"趋势评分仅 {score.trend:.0f}，短期动能偏弱。")

    if trend:
        evidence.append(
            f"展望 {trend.horizon_label}：方向 {trend.bias}，"
            f"偏多概率 {trend.probability_up:.0%}，趋势分 {trend.score:.0f}"
        )
        if trend.move_band_pct is not None:
            evidence.append(
                f"该周期 1σ 波动带宽约 ±{trend.move_band_pct:.1f}%（由年化波动换算，非收益预测）"
            )
        regime = (trend.details or {}).get("regime")
        if regime:
            evidence.append(f"市场体制（ADX）：{regime}；趋势强度 {trend.strength:.0f}")
            if regime == "震荡":
                risks.append("ADX 显示震荡市，趋势信号可信度下降，已向中性收缩。")
            elif regime == "趋势" and trend.bias == "偏多":
                why.append("ADX 确认趋势市，多头信号更可信。")
        st_dir = (trend.details or {}).get("supertrend_dir")
        if st_dir is not None:
            st_label = "多头轨上方" if int(st_dir) >= 1 else "空头轨下方"
            evidence.append(f"Supertrend：{st_label}")
        mtf = (trend.details or {}).get("mtf_align")
        if isinstance(mtf, dict) and mtf.get("agree") is not None:
            evidence.append(
                f"多周期对齐：一致 {mtf.get('agree', 0)}，冲突 {mtf.get('conflict', 0)}"
            )
            if int(mtf.get("conflict") or 0) > 0:
                risks.append("长短展望方向冲突，置信度已下调。")
        rsi_txt = "—" if trend.rsi is None else f"{trend.rsi:.0f}"
        mom_txt = "—" if trend.momentum_20d is None else f"{trend.momentum_20d:.1f}%"
        vol_txt = "—" if trend.volatility is None else f"{trend.volatility:.1f}%"
        evidence.append(
            f"均线：{trend.ma_signal}；MACD：{trend.macd_signal}；RSI={rsi_txt}；动量 {mom_txt}"
        )
        evidence.append(
            f"量能：{trend.volume_trend}；年化波动约 {vol_txt}；风险等级 {trend.risk_level}"
        )
        if trend.risk_level == "高":
            risks.append("波动偏高，短期回撤风险需控制仓位。")
        if trend.ma_signal == "空头排列":
            risks.append("均线空头排列，趋势尚未扭转前不宜重仓新开。")
        if trend.rsi is not None and trend.rsi >= 70:
            risks.append("RSI 进入超买区，短期回调概率上升。")
        if trend.rsi is not None and trend.rsi <= 30:
            why.append("RSI 进入超卖区，存在均值回归的逆向机会（非保证反弹）。")
        if trend.bias == "偏多":
            why.append(f"{trend.horizon_label}技术面偏多（置信度 {trend.probability_up:.0%}）。")
        elif trend.bias == "偏空":
            why_not.append(f"{trend.horizon_label}技术面偏空（置信度偏空侧）。")

    if score.capital >= 65:
        why.append(f"资金/量能维度得分 {score.capital:.0f}，量价配合较好。")
    elif score.capital <= 35:
        why_not.append(f"资金维度偏弱（{score.capital:.0f}），需警惕放量下跌或缩量阴跌。")

    if score.risk <= 40:
        risks.append(f"风险维度得分偏低（{score.risk:.0f}），建议降低单指数暴露。")

    stance = score.components.get("policy_stance")
    macro_label = score.components.get("macro_label")
    if score.macro >= 65:
        why.append(f"宏观环境偏友好（宏观分 {score.macro:.0f}，{macro_label or '宏观中性'}）。")
    elif score.macro <= 40:
        why_not.append(f"宏观承压（宏观分 {score.macro:.0f}），指数β收益可能受限。")
    if stance == "宽松" or score.policy >= 65:
        why.append(f"政策面偏宽松（政策分 {score.policy:.0f}，立场 {stance or '未知'}）。")
    elif stance == "偏紧" or score.policy <= 35:
        why_not.append(f"政策偏紧（政策分 {score.policy:.0f}），风险偏好可能受抑。")

    pmi = score.components.get("pmi")
    cpi = score.components.get("cpi")
    m2 = score.components.get("m2_yoy")
    lpr = score.components.get("lpr_1y")
    lpr_delta = score.components.get("lpr_delta")
    macro_bits = []
    if pmi is not None:
        macro_bits.append(f"PMI {pmi}")
    if cpi is not None:
        macro_bits.append(f"CPI {cpi}%")
    if m2 is not None:
        macro_bits.append(f"M2同比 {m2}%")
    if lpr is not None:
        delta_txt = "" if lpr_delta is None else f"（变动 {lpr_delta:+.2f}）"
        macro_bits.append(f"LPR1Y {lpr}%{delta_txt}")
    if macro_bits:
        evidence.append("宏观/政策：" + "；".join(macro_bits))

    if not why and score.label == "机会":
        why.append("多因子综合分较高，可作为观察池优先标的。")
    if not why_not and score.label == "谨慎":
        why_not.append("综合评分偏低，建议观望或仅用闲置定投额度试探。")

    summary = (
        f"「{score.index}」AI 综合分 {score.total:.1f}（{score.label}）。"
        f"估值 {score.valuation:.0f} / 趋势 {score.trend:.0f} / 资金 {score.capital:.0f} / "
        f"盈利 {score.earnings:.0f} / 风险 {score.risk:.0f} / 情绪 {score.sentiment:.0f} / "
        f"宏观 {score.macro:.0f} / 政策 {score.policy:.0f}。"
    )

    return Explanation(
        title=f"{score.index} · {score.label}",
        why_recommend=why,
        why_not=why_not,
        risk_sources=risks or ["常规市场波动风险"],
        evidence=evidence,
        summary=summary,
    )


def explain_action(action: str, index: str, context: dict[str, Any]) -> Explanation:
    """解释增持/减持/再平衡动作。"""
    why: list[str] = []
    why_not: list[str] = []
    risks: list[str] = []
    evidence: list[str] = []

    cur = context.get("current_pct")
    tgt = context.get("target_pct")
    label = context.get("valuation_label")
    pe_pct = context.get("percentile")
    score = context.get("ai_score")

    if pe_pct is not None:
        evidence.append(f"估值状态：{label}（百分位 {pe_pct:.1f}%）")
    if cur is not None and tgt is not None:
        evidence.append(f"当前仓位 {cur:.1f}% → 目标 {tgt:.1f}%")
    if score is not None:
        evidence.append(f"AI 综合分 {score:.1f}")

    if action == "增持":
        why.append("当前仓位低于估值/策略目标，补仓有助于回到计划配置。")
        if pe_pct is not None and pe_pct < 40:
            why.append("估值不高，适合用定投或分批加仓完成再平衡。")
        risks.append("加仓后若继续下跌会短期浮亏，应控制单次加仓比例。")
    elif action == "减持":
        why.append("当前仓位高于目标，减仓可锁定部分收益并降低回撤。")
        if pe_pct is not None and pe_pct > 70:
            why.append("估值偏高，继续加仓性价比下降。")
        risks.append("过早减仓可能踏空后续行情，建议按偏离度分批。")
    else:
        why.append("仓位与目标接近，维持定投节奏即可。")
        why_not.append("无需因短期波动频繁交易。")

    return Explanation(
        title=f"{index} · 建议{action}",
        why_recommend=why,
        why_not=why_not,
        risk_sources=risks or ["常规波动"],
        evidence=evidence,
        summary=f"对「{index}」给出「{action}」建议，详见证据与风险说明。",
    )
