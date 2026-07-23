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

from jijin.ui.constants import INDEX_GROUP_OPTIONS, INDEX_OPTIONS, score_cache_key
from jijin.ui.widgets import (
    header,
    panel_hint,
    position_change_list,
    render_horizon_line_chart,
    render_opportunity_list,
    render_trend_matrix,
    section_title,
)
from jijin.ui.state import (
    _enrich_holding_rows,
    _holdings_records,
    _invalidate_analysis_state,
    _sync_holdings_editor_state,
    get_cfg,
)
from jijin.ui.loading import (
    _compute_score_payload,
    loading_progress,
)

def page_parameters(cfg: dict[str, Any]) -> None:
    header(
        "策略参数",
        "高级设置：趋势、八因子评分、宏观与政策、自动校准",
    )
    trend = get_trend_settings(cfg)
    scoring = get_scoring_settings(cfg)
    macro = get_macro_settings(cfg)

    trend_tab, scoring_tab, macro_tab, auto_tab = st.tabs(
        ["趋势引擎", "AI 八因子评分", "宏观与政策", "自动校准"]
    )
    with trend_tab:
        panel_hint(
            "说明 · 默认展望周期用于机会排名与看板；权重保存时自动归一化。"
            "默认周期的指标窗口用本页配置，其他周期仍用内置时间尺度窗口。"
        )
        with st.form("trend_parameters"):
            horizon_options = list_trend_horizons()
            horizon_labels = {k: lab for k, lab, _ in horizon_options}
            cur_h = str(trend.get("default_horizon") or "1m")
            default_horizon_pick = st.selectbox(
                "默认展望周期（机会排名 / 看板）",
                options=[k for k, _, _ in horizon_options],
                index=[k for k, _, _ in horizon_options].index(cur_h)
                if cur_h in horizon_labels
                else 2,
                format_func=lambda k: horizon_labels.get(k, k),
            )
            enhancements = dict(trend.get("enhancements") or {})
            st.markdown("#### 专业增强（可开关）")
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                en_soft = st.checkbox(
                    "软均线分", value=bool(enhancements.get("soft_ma_score", True))
                )
            with e2:
                en_regime = st.checkbox(
                    "ADX 体制门控", value=bool(enhancements.get("regime_filter", True))
                )
            with e3:
                en_st = st.checkbox(
                    "Supertrend 确认",
                    value=bool(enhancements.get("supertrend_confirm", True)),
                )
            with e4:
                en_mtf = st.checkbox(
                    "多周期对齐",
                    value=bool(enhancements.get("multi_horizon_align", True)),
                )

            st.markdown("#### 技术指标周期")
            c1, c2, c3, c4 = st.columns(4)
            indicators = trend["indicators"]
            with c1:
                ma_short = st.number_input(
                    "短期 SMA", 2, 250, int(indicators["ma_short"])
                )
                ma_medium = st.number_input(
                    "中期 SMA", 3, 500, int(indicators["ma_medium"])
                )
                ma_long = st.number_input(
                    "长期 SMA", 5, 1000, int(indicators["ma_long"])
                )
            with c2:
                macd_fast = st.number_input(
                    "MACD 快线", 2, 100, int(indicators["macd_fast"])
                )
                macd_slow = st.number_input(
                    "MACD 慢线", 3, 200, int(indicators["macd_slow"])
                )
                macd_signal = st.number_input(
                    "MACD 信号线", 2, 100, int(indicators["macd_signal"])
                )
            with c3:
                rsi_length = st.number_input(
                    "RSI 周期", 2, 100, int(indicators["rsi_length"])
                )
                roc_length = st.number_input(
                    "ROC 动量周期", 2, 250, int(indicators["roc_length"])
                )
                adx_length = st.number_input(
                    "ADX 周期", 2, 100, int(indicators["adx_length"])
                )
            with c4:
                volatility_window = st.number_input(
                    "波动率窗口", 10, 500, int(indicators["volatility_window"])
                )
                volume_window = st.number_input(
                    "量能窗口", 5, 250, int(indicators["volume_window"])
                )

            st.markdown("#### 趋势分权重 %")
            weights = trend["weights"]
            weight_cols = st.columns(5)
            trend_weight_values = {}
            for col, key, label in zip(
                weight_cols,
                ["ma", "macd", "rsi", "momentum", "volume"],
                ["均线", "MACD", "RSI", "动量", "量能"],
            ):
                with col:
                    trend_weight_values[key] = st.number_input(
                        label,
                        0.0,
                        100.0,
                        float(weights[key] * 100),
                        1.0,
                        key=f"tw_{key}",
                    )
            st.caption(
                f"当前输入合计：{sum(trend_weight_values.values()):.1f}%（无需手工凑到100）"
            )

            st.markdown("#### 信号与风险阈值")
            thresholds = trend["thresholds"]
            t1, t2, t3, t4 = st.columns(4)
            with t1:
                rsi_oversold = st.number_input(
                    "RSI 超卖", 1.0, 49.0, float(thresholds["rsi_oversold"]), 1.0
                )
                rsi_overbought = st.number_input(
                    "RSI 超买", 51.0, 99.0, float(thresholds["rsi_overbought"]), 1.0
                )
            with t2:
                volume_expand = st.number_input(
                    "放量倍数",
                    1.0,
                    5.0,
                    float(thresholds["volume_expand_ratio"]),
                    0.05,
                )
                volume_contract = st.number_input(
                    "缩量倍数",
                    0.1,
                    1.0,
                    float(thresholds["volume_contract_ratio"]),
                    0.05,
                )
            with t3:
                risk_vol_medium = st.number_input(
                    "中风险波动率%",
                    1.0,
                    100.0,
                    float(thresholds["risk_volatility_medium"]),
                    1.0,
                )
                adx_trend_min = st.number_input(
                    "ADX 趋势线",
                    10.0,
                    50.0,
                    float(thresholds.get("adx_trend_min", 25)),
                    1.0,
                )
            with t4:
                risk_vol_high = st.number_input(
                    "高风险波动率%",
                    1.0,
                    150.0,
                    float(thresholds["risk_volatility_high"]),
                    1.0,
                )
                adx_range_max = st.number_input(
                    "ADX 震荡线",
                    5.0,
                    40.0,
                    float(thresholds.get("adx_range_max", 20)),
                    1.0,
                )

            save_trend = st.form_submit_button(
                "保存趋势参数", type="primary", width="stretch"
            )

        if save_trend:
            if not (ma_short < ma_medium < ma_long):
                st.error("SMA 周期必须满足：短期 < 中期 < 长期")
            elif macd_fast >= macd_slow:
                st.error("MACD 快线周期必须小于慢线周期")
            elif risk_vol_medium > risk_vol_high:
                st.error("中风险波动率不能高于高风险波动率")
            elif adx_range_max > adx_trend_min:
                st.error("ADX 震荡线不能高于趋势线")
            else:
                prev = dict(cfg.get("trend") or {})
                cfg["trend"] = {
                    **prev,
                    "default_horizon": default_horizon_pick,
                    "indicators": {
                        "ma_short": int(ma_short),
                        "ma_medium": int(ma_medium),
                        "ma_long": int(ma_long),
                        "macd_fast": int(macd_fast),
                        "macd_slow": int(macd_slow),
                        "macd_signal": int(macd_signal),
                        "rsi_length": int(rsi_length),
                        "roc_length": int(roc_length),
                        "adx_length": int(adx_length),
                        "volatility_window": int(volatility_window),
                        "volume_window": int(volume_window),
                    },
                    "weights": {
                        key: value / 100
                        for key, value in trend_weight_values.items()
                    },
                    "thresholds": {
                        **dict(prev.get("thresholds") or {}),
                        "rsi_oversold": float(rsi_oversold),
                        "rsi_overbought": float(rsi_overbought),
                        "volume_expand_ratio": float(volume_expand),
                        "volume_contract_ratio": float(volume_contract),
                        "risk_volatility_medium": float(risk_vol_medium),
                        "risk_volatility_high": float(risk_vol_high),
                        "adx_trend_min": float(adx_trend_min),
                        "adx_range_max": float(adx_range_max),
                    },
                    "enhancements": {
                        "soft_ma_score": bool(en_soft),
                        "regime_filter": bool(en_regime),
                        "supertrend_confirm": bool(en_st),
                        "multi_horizon_align": bool(en_mtf),
                    },
                }
                save_config(cfg)
                st.session_state.cfg = load_config()
                _invalidate_analysis_state()
                st.success("趋势参数已保存；权重已在计算时自动归一化。")
                st.rerun()

    with scoring_tab:
        panel_hint(
            "说明 · 八因子权重保存时自动归一化为 100%。"
            "关闭宏观模块后，宏观/政策权重会并入估值与趋势。"
        )
        with st.form("scoring_parameters"):
            st.markdown("#### 八因子权重 %")
            weights = scoring["weights"]
            cols = st.columns(4)
            scoring_weight_values = {}
            score_items = [
                ("valuation", "估值"),
                ("trend", "趋势"),
                ("capital", "资金"),
                ("earnings", "盈利"),
                ("risk", "风险"),
                ("sentiment", "情绪"),
                ("macro", "宏观"),
                ("policy", "政策"),
            ]
            for i, (key, label) in enumerate(score_items):
                with cols[i % 4]:
                    scoring_weight_values[key] = st.number_input(
                        label,
                        0.0,
                        100.0,
                        float(weights[key] * 100),
                        1.0,
                        key=f"sw_{key}",
                    )
            st.caption(
                f"当前输入合计：{sum(scoring_weight_values.values()):.1f}%（无需手工凑到100）"
            )

            st.markdown("#### 标签阈值")
            label_cols = st.columns(2)
            labels = scoring["labels"]
            with label_cols[0]:
                neutral_min = st.number_input(
                    "中性最低分",
                    0.0,
                    100.0,
                    float(labels["neutral_min"]),
                    1.0,
                )
            with label_cols[1]:
                opportunity_min = st.number_input(
                    "机会最低分",
                    0.0,
                    100.0,
                    float(labels["opportunity_min"]),
                    1.0,
                )
            save_scoring = st.form_submit_button(
                "保存评分参数", type="primary", width="stretch"
            )

        if save_scoring:
            if neutral_min > opportunity_min:
                st.error("中性最低分不能高于机会最低分")
            else:
                cfg["scoring"] = {
                    "weights": {
                        key: value / 100
                        for key, value in scoring_weight_values.items()
                    },
                    "labels": {
                        "neutral_min": float(neutral_min),
                        "opportunity_min": float(opportunity_min),
                    },
                }
                save_config(cfg)
                st.session_state.cfg = load_config()
                _invalidate_analysis_state()
                st.success("评分参数已保存；权重已在计算时自动归一化。")

    with macro_tab:
        panel_hint(
            "说明 · PMI / CPI / M2 / LPR 来自公开数据；政策立场可自动推断，也可手工覆盖。"
        )
        with st.form("macro_parameters"):
            enabled = st.checkbox("启用宏观与政策因子", value=bool(macro["enabled"]))
            st.markdown("#### 宏观内部分项权重 %")
            mw = macro["weights"]
            mcols = st.columns(3)
            macro_weight_values = {}
            for col, key, label in zip(
                mcols,
                ["pmi", "cpi", "liquidity"],
                ["制造业 PMI", "CPI", "流动性(M2)"],
            ):
                with col:
                    macro_weight_values[key] = st.number_input(
                        label,
                        0.0,
                        100.0,
                        float(mw[key] * 100),
                        1.0,
                        key=f"mw_{key}",
                    )

            st.markdown("#### 阈值")
            th = macro["thresholds"]
            t1, t2, t3 = st.columns(3)
            with t1:
                pmi_expansion = st.number_input("PMI 荣枯线", 40.0, 60.0, float(th["pmi_expansion"]), 0.1)
                pmi_strong = st.number_input("PMI 强扩张", 45.0, 65.0, float(th["pmi_strong"]), 0.1)
            with t2:
                cpi_low = st.number_input("CPI 偏低线%", -2.0, 5.0, float(th["cpi_low"]), 0.1)
                cpi_comfort_high = st.number_input("CPI 舒适上限%", 0.0, 8.0, float(th["cpi_comfort_high"]), 0.1)
                cpi_high = st.number_input("CPI 偏高线%", 1.0, 12.0, float(th["cpi_high"]), 0.1)
            with t3:
                m2_soft = st.number_input("M2 偏弱线%", 0.0, 20.0, float(th["m2_soft"]), 0.1)
                m2_comfort = st.number_input("M2 舒适上限%", 0.0, 25.0, float(th["m2_comfort"]), 0.1)
                m2_hot = st.number_input("M2 过热线%", 0.0, 30.0, float(th["m2_hot"]), 0.1)

            st.markdown("#### 政策立场")
            stance_options = [
                ("auto", "自动（依据 LPR 变动 + M2）"),
                ("easing", "宽松"),
                ("neutral", "中性"),
                ("tightening", "偏紧"),
            ]
            current_stance = str(macro["policy"].get("stance") or "auto").lower()
            stance_alias = {
                "auto": 0,
                "自动": 0,
                "easing": 1,
                "宽松": 1,
                "neutral": 2,
                "中性": 2,
                "tightening": 3,
                "偏紧": 3,
            }
            stance_choice = st.selectbox(
                "立场",
                stance_options,
                index=stance_alias.get(current_stance, 0),
                format_func=lambda x: x[1],
            )
            use_manual = st.checkbox(
                "手工指定政策分",
                value=macro["policy"].get("manual_score") is not None,
            )
            manual_score = st.number_input(
                "政策分（0-100）",
                0.0,
                100.0,
                float(macro["policy"].get("manual_score") or 55),
                1.0,
                disabled=not use_manual,
            )
            save_macro = st.form_submit_button(
                "保存宏观与政策参数", type="primary", width="stretch"
            )

        if save_macro:
            if pmi_expansion > pmi_strong:
                st.error("PMI 荣枯线不能高于强扩张线")
            elif cpi_low > cpi_comfort_high or cpi_comfort_high > cpi_high:
                st.error("CPI 阈值需满足：偏低线 ≤ 舒适上限 ≤ 偏高线")
            elif m2_soft > m2_comfort or m2_comfort > m2_hot:
                st.error("M2 阈值需满足：偏弱线 ≤ 舒适上限 ≤ 过热线")
            else:
                cfg["macro"] = {
                    "enabled": bool(enabled),
                    "weights": {key: value / 100 for key, value in macro_weight_values.items()},
                    "thresholds": {
                        "pmi_expansion": float(pmi_expansion),
                        "pmi_strong": float(pmi_strong),
                        "cpi_low": float(cpi_low),
                        "cpi_comfort_high": float(cpi_comfort_high),
                        "cpi_high": float(cpi_high),
                        "m2_soft": float(m2_soft),
                        "m2_comfort": float(m2_comfort),
                        "m2_hot": float(m2_hot),
                    },
                    "policy": {
                        "stance": stance_choice[0],
                        "manual_score": float(manual_score) if use_manual else None,
                    },
                }
                save_config(cfg)
                st.session_state.cfg = load_config()
                _invalidate_analysis_state()
                st.success("宏观与政策参数已保存。")

    with auto_tab:
        panel_hint(
            "说明 · 用近约 5 年指数日线做 Walk-Forward（滚动样本外）粗网格搜索："
            "在训练窗选参数，在测试窗评估方向命中率、Spearman IC 与简化多空 Sharpe；"
            "最优解向默认参数收缩，且仅当样本外明显优于默认才建议写回，降低过拟合。"
        )
        cal = dict(cfg.get("calibration") or {})
        c1, c2, c3 = st.columns(3)
        with c1:
            cal_years = st.number_input(
                "回看年数", 2.0, 8.0, float(cal.get("years", 5.0)), 0.5
            )
            cal_forward = st.number_input(
                "前瞻交易日", 5, 63, int(cal.get("forward_days", 21)), 1
            )
        with c2:
            cal_train = st.number_input(
                "训练窗(交易日)", 126, 756, int(cal.get("train_days", 504)), 21
            )
            cal_test = st.number_input(
                "测试窗(交易日)", 21, 126, int(cal.get("test_days", 63)), 21
            )
        with c3:
            cal_step = st.number_input(
                "滚动步长", 21, 126, int(cal.get("step_days", 63)), 21
            )
            cal_shrink = st.slider(
                "向默认收缩",
                0.0,
                0.8,
                float(cal.get("shrinkage", 0.35)),
                0.05,
                help="越大越保守，越接近内置默认权重",
            )
        force_cal = st.checkbox("强制刷新行情缓存", value=False)
        run_cal = st.button("运行自动校准", type="primary", width="stretch")

        if run_cal:
            cfg["calibration"] = {
                **cal,
                "years": float(cal_years),
                "forward_days": int(cal_forward),
                "train_days": int(cal_train),
                "test_days": int(cal_test),
                "step_days": int(cal_step),
                "shrinkage": float(cal_shrink),
            }
            save_config(cfg)
            with loading_progress("自动校准") as progress:
                progress(0, 1, "拉取行情并 Walk-Forward…")
                result = calibrate_agent(cfg, force=force_cal, write_back=False)
                progress(1, 1, "完成")
            st.session_state["cal_result"] = result

        result = st.session_state.get("cal_result")
        if result is not None:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("样本外命中率", f"{result.best_oos.hit_rate:.1%}")
            m2.metric("样本外 IC", f"{result.best_oos.ic:.3f}")
            m3.metric("样本外 Sharpe", f"{result.best_oos.sharpe:.2f}")
            m4.metric("滚动折数", f"{result.folds}")
            st.write(
                f"指数：{', '.join(result.indexes_used) or '-'}　｜　"
                f"中位历史长度 {result.lookback_days} 日　｜　"
                f"前瞻 {result.forward_days} 日　｜　收缩 {result.shrinkage:.0%}"
            )
            st.info(result.reason)
            w = result.best_trend.get("weights") or {}
            st.markdown(
                "建议权重："
                + "　".join(
                    f"{k.upper()} {float(w.get(k, 0)) * 100:.0f}%"
                    for k in ["ma", "macd", "rsi", "momentum", "volume"]
                )
            )
            with st.expander("对比默认 / 候选（样本外）"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "方案": "当前默认基线",
                                "命中率": round(result.default_oos.hit_rate, 4),
                                "IC": round(result.default_oos.ic, 4),
                                "Sharpe": round(result.default_oos.sharpe, 4),
                            },
                            {
                                "方案": "最优候选(收缩前评估)",
                                "命中率": round(result.best_oos.hit_rate, 4),
                                "IC": round(result.best_oos.ic, 4),
                                "Sharpe": round(result.best_oos.sharpe, 4),
                            },
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
            apply_cols = st.columns(2)
            with apply_cols[0]:
                if st.button(
                    "应用建议参数到趋势引擎",
                    type="primary",
                    width="stretch",
                    disabled=not result.indexes_used,
                ):
                    merged_trend = {
                        **dict(cfg.get("trend") or {}),
                        **dict(result.best_trend or {}),
                    }
                    if (cfg.get("trend") or {}).get("enhancements") and not merged_trend.get(
                        "enhancements"
                    ):
                        merged_trend["enhancements"] = deepcopy(
                            cfg["trend"]["enhancements"]
                        )
                    cfg["trend"] = to_yaml_safe(merged_trend)
                    cfg["calibration"] = to_yaml_safe(
                        {
                            **dict(cfg.get("calibration") or {}),
                            "last_run": {
                                "accepted": result.accepted,
                                "reason": result.reason,
                                "indexes": result.indexes_used,
                                "folds": result.folds,
                                "default_oos": {
                                    "hit_rate": float(result.default_oos.hit_rate),
                                    "ic": float(result.default_oos.ic),
                                    "sharpe": float(result.default_oos.sharpe),
                                    "samples": int(result.default_oos.samples),
                                },
                                "best_oos": {
                                    "hit_rate": float(result.best_oos.hit_rate),
                                    "ic": float(result.best_oos.ic),
                                    "sharpe": float(result.best_oos.sharpe),
                                    "samples": int(result.best_oos.samples),
                                },
                                "details": result.details,
                            },
                        }
                    )
                    save_config(cfg)
                    st.session_state.cfg = load_config()
                    _invalidate_analysis_state()
                    st.success("已写入 config.yaml 的 trend 节；请到「趋势引擎」核对。")
                    st.rerun()
            with apply_cols[1]:
                if result.accepted:
                    st.caption("已通过稳健性门槛，建议应用。")
                else:
                    st.caption("未通过门槛：可仍手工应用，但更易过拟合。")

    st.markdown("---")
    confirm_reset = st.checkbox("确认恢复全部默认（趋势 / 评分 / 宏观）", value=False)
    if st.button(
        "恢复趋势 / 评分 / 宏观默认参数",
        width="stretch",
        disabled=not confirm_reset,
    ):
        cfg["trend"] = deepcopy(DEFAULT_TREND_SETTINGS)
        cfg["scoring"] = deepcopy(DEFAULT_SCORING_SETTINGS)
        cfg["macro"] = deepcopy(DEFAULT_MACRO_SETTINGS)
        save_config(cfg)
        st.session_state.cfg = load_config()
        _invalidate_analysis_state()
        st.success("已恢复默认参数")
        st.rerun()


