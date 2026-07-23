from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from html import escape
import json
import re
from typing import Any, Callable, Iterator

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from jijin.agents import (
    build_dashboard,
    calibrate_agent,
    coach_agent,
    opportunity_agent,
    portfolio_agent,
    score_agent,
    trend_horizons_agent,
)
from jijin.alert.smart import generate_smart_alerts
from jijin.config import cache_dir, load_config, save_config, to_yaml_safe
from jijin.data.cache import CacheStore
from jijin.data.fund import lookup_fund_by_code
from jijin.data.market import INDEX_GROUPS, INDEX_SYMBOLS
from jijin.portfolio.holdings import apply_strategy_to_holdings
from jijin.engine.settings import (
    DEFAULT_MACRO_SETTINGS,
    DEFAULT_SCORING_SETTINGS,
    DEFAULT_TREND_SETTINGS,
    get_macro_settings,
    get_scoring_settings,
    get_trend_settings,
    list_trend_horizons,
)
from jijin.screener.opportunity import (
    market_index_universe,
    opportunities_to_rows,
    opportunity_scan_errors,
)
from jijin.strategy.generator import RISK_PROFILES, STRATEGY_TEMPLATES

from jijin.ui.constants import INDEX_OPTIONS

def header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
<div class="brand-wrap">
  <div class="brand-accent" aria-hidden="true"></div>
  <div>
    <p class="brand-kicker">AI Index · 指数决策助手</p>
    <p class="brand-title">{escape(title)}</p>
    <p class="brand-sub">{escape(subtitle)}</p>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str) -> None:
    st.markdown(f'<p class="section-title">{title}</p>', unsafe_allow_html=True)


def panel_hint(text: str, *, label: str = "说明") -> None:
    """Tab 内说明：独立提示条，避免与切换项视觉混淆。"""
    body = text.strip()
    for prefix in (f"{label} · ", f"{label}· ", f"{label}·", f"{label}：", f"{label}:"):
        if body.startswith(prefix):
            body = body[len(prefix) :].lstrip()
            break
    st.markdown(
        f"""
<div class="panel-hint">
  <span class="panel-hint-label">{escape(label)}</span>
  <p class="panel-hint-text">{escape(body)}</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def _trend_cell_color(score: float | None) -> str:
    """趋势分映射到绿(跌)→灰→红(涨)的浅色底，符合 A 股习惯。"""
    if score is None:
        return "#f3f5f4"
    s = max(0.0, min(100.0, float(score)))
    if s >= 50:
        t = (s - 50) / 50  # 0..1 越大越红（偏多）
        r, g, b = 255, 243 - int(90 * t), 243 - int(90 * t)
    else:
        t = (50 - s) / 50  # 0..1 越大越绿（偏空）
        r, g, b = 238 - int(150 * t), 248 - int(20 * t), 243 - int(80 * t)
    return f"rgb({r},{g},{b})"


def _sorted_horizon_results(results: list[Any]) -> list[Any]:
    """按展望交易日数从小到大排序，避免中文标签被字母序打乱。"""
    return sorted(results, key=lambda tr: (int(getattr(tr, "horizon_days", 0) or 0), str(tr.horizon)))


def _normalize_trend_multi(multi: dict[str, list[Any]]) -> dict[str, list[Any]]:
    return {name: _sorted_horizon_results(results) for name, results in multi.items()}


def _horizon_axis_order(multi: dict[str, list[Any]]) -> list[str]:
    for results in multi.values():
        return [tr.horizon_label for tr in _sorted_horizon_results(results)]
    return []


def render_horizon_line_chart(
    multi: dict[str, list[Any]],
    *,
    value_attr: str,
    value_title: str,
    y_domain: list[float] | None = None,
) -> None:
    """用 Altair 固定横轴为 1天→1年，避免 st.line_chart 按中文拼音/字典序重排。"""
    multi = _normalize_trend_multi(multi)
    order = _horizon_axis_order(multi)
    if not order:
        return
    rows = []
    for name, results in multi.items():
        for tr in results:
            rows.append(
                {
                    "指数": name,
                    "周期": tr.horizon_label,
                    "交易日": int(tr.horizon_days),
                    value_title: float(getattr(tr, value_attr)),
                }
            )
    chart_df = pd.DataFrame(rows)
    y_enc = alt.Y(f"{value_title}:Q", title=value_title)
    if y_domain is not None:
        y_enc = alt.Y(f"{value_title}:Q", title=value_title, scale=alt.Scale(domain=y_domain))
    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("周期:N", sort=order, title="展望周期"),
            y=y_enc,
            color=alt.Color(
                "指数:N",
                legend=alt.Legend(title="指数"),
                scale=alt.Scale(
                    range=["#0a6e5c", "#2f8f78", "#4aa88f", "#c45c4a", "#a96510", "#3d6b8c"]
                ),
            ),
            tooltip=["指数", "周期", "交易日", value_title],
        )
        .properties(height=300)
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor="#5f6d69",
            titleColor="#142421",
            gridColor="#e3ece8",
            domainColor="#d5e2dc",
        )
    )
    st.altair_chart(chart, width="stretch")


def render_trend_matrix(multi: dict[str, list[Any]]) -> None:
    """指数 × 展望周期 的趋势热力矩阵。"""
    multi = _normalize_trend_multi(multi)
    if not multi:
        return
    horizon_labels = _horizon_axis_order(multi)

    head = "".join(f"<th>{escape(h)}</th>" for h in horizon_labels)
    body_rows = []
    for name, results in multi.items():
        by_label = {tr.horizon_label: tr for tr in results}
        cells = []
        for label in horizon_labels:
            tr = by_label.get(label)
            if tr is None:
                cells.append("<td>—</td>")
                continue
            color = _trend_cell_color(tr.score)
            prob = f"{tr.probability_up:.0%}"
            band = "" if tr.move_band_pct is None else f" ±{tr.move_band_pct:.0f}%"
            cells.append(
                f'<td style="background:{color}">'
                f'<div class="tm-cell"><span class="tm-bias">{escape(tr.bias)}</span>'
                f'<span class="tm-score">{tr.score:.0f} · {prob}{band}</span></div></td>'
            )
        body_rows.append(f"<tr><th>{escape(name)}</th>{''.join(cells)}</tr>")

    st.markdown(
        f'<table class="trend-matrix"><thead><tr><th>指数 \\ 周期</th>{head}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div class="tm-legend">
  <span class="tm-chip"><span class="tm-swatch" style="background:rgb(255,153,153)"></span>偏多 / 涨</span>
  <span class="tm-chip"><span class="tm-swatch" style="background:#f3f5f4"></span>中性</span>
  <span class="tm-chip"><span class="tm-swatch" style="background:rgb(88,228,163)"></span>偏空 / 跌</span>
  <span>单元格：方向 · 趋势分 · 偏多概率 · 波动带宽</span>
</div>
        """,
        unsafe_allow_html=True,
    )


def position_change_list(advices: list[Any], explanations: dict[str, Any]) -> None:
    actionable = sorted(
        [a for a in advices if a.action in {"增持", "减持"}],
        key=lambda a: abs(a.delta_pct),
        reverse=True,
    )
    stable = [a for a in advices if a.action not in {"增持", "减持"}]

    if not actionable:
        st.success("仓位均在目标范围内，暂不需要调整")
    else:
        add_amount = sum(max(0.0, a.suggest_amount) for a in actionable)
        reduce_amount = sum(abs(min(0.0, a.suggest_amount)) for a in actionable)
        st.markdown(
            f"""
<div class="position-summary">
  <span><strong>{len(actionable)}</strong> 项需调整</span>
  <span>增持约 <strong>¥{add_amount:,.0f}</strong></span>
  <span>减持约 <strong>¥{reduce_amount:,.0f}</strong></span>
</div>
            """,
            unsafe_allow_html=True,
        )
        rows = []
        for a in actionable:
            tone = "buy" if a.action == "增持" else "sell"
            sign = "+" if a.delta_pct > 0 else "−"
            amount_sign = "+" if a.suggest_amount > 0 else "−"
            percentile = "暂无百分位" if a.percentile is None else f"{a.metric.upper()} 分位 {a.percentile:.0f}%"
            rows.append(
                f"""
<div class="position-row">
  <div class="position-name">{escape(a.index)}<small>{escape(a.label)} · {percentile}</small></div>
  <div class="position-action {tone}">{a.action}</div>
  <div class="position-change">{a.current_pct:.1f}%<span class="arrow">→</span>{a.target_pct:.1f}%</div>
  <div class="position-delta {tone}">{sign}{abs(a.delta_pct):.1f}pct</div>
  <div class="position-amount">{amount_sign}¥{abs(a.suggest_amount):,.0f}</div>
</div>
                """
            )
        st.markdown(
            '<div class="position-list">' + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )

        with st.expander("查看调整依据"):
            for a in actionable:
                exp = explanations.get(f"action:{a.index}")
                st.markdown(f"**{a.index} · {a.action}**")
                if exp:
                    st.write(exp.summary)
                    reasons = exp.why_recommend + exp.risk_sources
                    for item in reasons:
                        st.write(f"- {item}")
                else:
                    st.caption(a.message)

    if stable:
        with st.expander(f"无需调整 / 数据不足（{len(stable)}）"):
            stable_df = pd.DataFrame(
                [
                    {
                        "指数": a.index,
                        "状态": a.action,
                        "当前": f"{a.current_pct:.1f}%",
                        "目标": f"{a.target_pct:.1f}%",
                        "估值": a.label,
                    }
                    for a in stable
                ]
            )
            st.dataframe(stable_df, width="stretch", hide_index=True)


def render_opportunity_list(items: list[Any], horizon_label: str) -> None:
    if not items:
        st.caption("暂无可用的市场指数机会")
        return
    st.markdown(
        f"""
<div class="dash-lead">
  <div class="note">扫描宽基与行业指数 · 展望「{escape(horizon_label)}」· 按上涨概率排序</div>
  <div class="note">首位 <strong>{escape(items[0].index)}</strong> · {items[0].probability_up:.0%}</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    rows = []
    for item in items:
        if (getattr(item, "details", None) or {}).get("empty"):
            continue
        tone = "up" if item.bias == "偏多" else ("down" if item.bias == "偏空" else "flat")
        top = " top" if item.rank <= 3 else ""
        band = "—" if item.move_band_pct is None else f"±{item.move_band_pct:.0f}%"
        regime = (getattr(item, "details", None) or {}).get("regime") or ""
        meta_extra = f"{escape(regime)} · " if regime else ""
        rows.append(
            f"""
<div class="opp-row{top}">
  <div class="opp-rank">#{item.rank}</div>
  <div class="opp-name">{escape(item.index)}</div>
  <div class="opp-bias {tone}">{escape(item.bias)}</div>
  <div class="opp-prob">{item.probability_up:.0%}</div>
  <div class="opp-meta">趋势 {item.trend_score:.0f}</div>
  <div class="opp-meta">{meta_extra}{escape(item.risk_level)} · {band}</div>
</div>
            """
        )
    if not rows:
        st.caption("暂无可用的市场指数机会")
        return
    st.markdown('<div class="opp-list">' + "".join(rows) + "</div>", unsafe_allow_html=True)


