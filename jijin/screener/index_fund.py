from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from jijin.config import load_config
from jijin.data.fund import enrich_fund_fees, fetch_index_fund_table

# 一键预设（对齐天天基金/社区常见筛法）
SCREEN_PRESETS: dict[str, dict[str, Any]] = {
    "low_cost": {
        "label": "低费率宽基",
        "desc": "宽基 + A类 + 规模≥2亿 + 申购费≤0.15%，按费率排序",
        "index_keywords": ["沪深300", "中证500", "中证1000", "上证50", "创业板"],
        "share_class": "A",
        "min_scale_yi": 2.0,
        "max_purchase_fee": 0.15,
        "subtype_mode": "passive",
        "exclude_keywords": ["QDII", "联接C"],
        "sort_by": "fee_asc",
        "top_n": 30,
        "rule_4433": False,
    },
    "large_scale": {
        "label": "大规模稳健",
        "desc": "宽基 + 规模≥10亿，降低清盘与冲击成本风险",
        "index_keywords": ["沪深300", "中证500", "中证1000", "上证50"],
        "share_class": "A",
        "min_scale_yi": 10.0,
        "max_purchase_fee": 0.2,
        "subtype_mode": "passive",
        "exclude_keywords": ["QDII"],
        "sort_by": "scale_desc",
        "top_n": 30,
        "rule_4433": False,
    },
    "rule_4433": {
        "label": "4433 动量优选",
        "desc": "近1年/2年/3年收益均高于同类中位数，且今年来为正（指数基金近似版）",
        "index_keywords": [],
        "share_class": "A",
        "min_scale_yi": 2.0,
        "max_purchase_fee": 0.2,
        "subtype_mode": "all",
        "exclude_keywords": ["QDII"],
        "sort_by": "score_desc",
        "top_n": 40,
        "rule_4433": True,
    },
    "enhanced": {
        "label": "指数增强",
        "desc": "名称含「增强」+ 规模≥2亿，按近1年收益排序",
        "index_keywords": ["沪深300", "中证500", "中证1000"],
        "share_class": "A",
        "min_scale_yi": 2.0,
        "max_purchase_fee": 1.5,
        "subtype_mode": "enhanced",
        "exclude_keywords": [],
        "sort_by": "ret_1y_desc",
        "top_n": 30,
        "rule_4433": False,
    },
    "etf_link": {
        "label": "ETF联接",
        "desc": "场外联接产品，适合定投账户",
        "index_keywords": ["沪深300", "中证500", "中证1000", "创业板", "科创50"],
        "share_class": "A",
        "min_scale_yi": 2.0,
        "max_purchase_fee": 0.15,
        "subtype_mode": "etf_link",
        "exclude_keywords": [],
        "sort_by": "fee_asc",
        "top_n": 30,
        "rule_4433": False,
    },
    "undervalued": {
        "label": "低估宽基",
        "desc": "跟踪指数 PE 百分位 ≤40，适合中长期布局",
        "index_keywords": ["沪深300", "中证500", "中证1000", "上证50", "创业板"],
        "share_class": "A",
        "min_scale_yi": 2.0,
        "max_purchase_fee": 0.2,
        "max_pe_percentile": 40,
        "attach_index_metrics": True,
        "subtype_mode": "passive",
        "exclude_keywords": ["QDII"],
        "sort_by": "score_desc",
        "top_n": 30,
        "rule_4433": False,
    },
}

DISPLAY_COLUMNS = [
    ("code", "代码"),
    ("name", "名称"),
    ("tracked_index", "跟踪指数"),
    ("subtype", "类型"),
    ("share_class", "份额"),
    ("scale_yi", "规模(亿)"),
    ("purchase_fee", "申购费%"),
    ("total_fee", "综合费率%"),
    ("pe_percentile", "PE百分位"),
    ("pb_percentile", "PB百分位"),
    ("ai_score", "AI分"),
    ("nav", "净值"),
    ("ret_ytd", "今年来%"),
    ("ret_1y", "近1年%"),
    ("ret_2y", "近2年%"),
    ("ret_3y", "近3年%"),
    ("score", "综合分"),
]


def apply_preset(cfg: dict[str, Any], preset_key: str) -> dict[str, Any]:
    preset = SCREEN_PRESETS[preset_key]
    sc = dict(cfg.get("screen") or {})
    for k, v in preset.items():
        if k in {"label", "desc"}:
            continue
        sc[k] = v
    cfg = dict(cfg)
    cfg["screen"] = sc
    return cfg


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _match_share_class(series: pd.Series, want: str) -> pd.Series:
    w = (want or "ALL").upper()
    if w in {"", "ALL", "*"}:
        return pd.Series(True, index=series.index)
    return series.str.upper() == w


def _match_subtype(df: pd.DataFrame, mode: str) -> pd.Series:
    mode = (mode or "all").lower()
    name = df["name"].astype(str)
    subtype = df.get("subtype", pd.Series("", index=df.index)).astype(str)
    if mode in {"", "all"}:
        return pd.Series(True, index=df.index)
    if mode == "passive":
        return ~(
            name.str.contains("增强", na=False)
            | subtype.str.contains("增强", na=False)
        )
    if mode == "enhanced":
        return name.str.contains("增强", na=False) | subtype.str.contains("增强", na=False)
    if mode == "etf_link":
        return name.str.contains("联接", na=False) | subtype.str.contains("联接", na=False)
    if mode == "etf":
        return name.str.contains("ETF", na=False) & ~name.str.contains("联接", na=False)
    return pd.Series(True, index=df.index)


def _apply_4433(df: pd.DataFrame) -> pd.Series:
    """指数基金近似 4433：近1/2/3年收益均高于截面中位数，且今年来>0。"""
    mask = pd.Series(True, index=df.index)
    for col in ["ret_1y", "ret_2y", "ret_3y"]:
        if col not in df.columns:
            continue
        s = _to_num(df[col])
        med = s.median(skipna=True)
        if pd.isna(med):
            continue
        mask &= s.isna() | (s >= med)
    if "ret_ytd" in df.columns:
        ytd = _to_num(df["ret_ytd"])
        mask &= ytd.isna() | (ytd > 0)
    return mask


def _score_funds(df: pd.DataFrame) -> pd.Series:
    """综合分 0~100：规模、低费率、中长期收益。"""
    n = len(df)
    if n == 0:
        return pd.Series(dtype=float)

    def rank_pct(s: pd.Series, ascending: bool = True) -> pd.Series:
        x = _to_num(s)
        if x.notna().sum() == 0:
            return pd.Series(50.0, index=df.index)
        return x.rank(ascending=ascending, pct=True, na_option="keep") * 100

    # 费率越低越好；规模/收益越高越好
    fee = df["purchase_fee"] if "purchase_fee" in df.columns else pd.Series(np.nan, index=df.index)
    if "total_fee" in df.columns and df["total_fee"].notna().any():
        fee = df["total_fee"].fillna(fee)

    score = (
        0.35 * rank_pct(fee, ascending=True).fillna(50)
        + 0.25 * rank_pct(df.get("scale_yi", pd.Series(np.nan, index=df.index)), ascending=False).fillna(50)
        + 0.25 * rank_pct(df.get("ret_1y", pd.Series(np.nan, index=df.index)), ascending=False).fillna(50)
        + 0.15 * rank_pct(df.get("ret_3y", pd.Series(np.nan, index=df.index)), ascending=False).fillna(50)
    )
    return score.round(1)


def _attach_index_metrics(df: pd.DataFrame, cfg: dict[str, Any], force: bool = False) -> pd.DataFrame:
    """为基金结果挂载跟踪指数的 PE/PB 百分位与 AI 分。"""
    if df.empty or "tracked_index" not in df.columns:
        return df
    from jijin.engine.scoring import compute_ai_score

    indexes = sorted({str(x) for x in df["tracked_index"].dropna().unique() if str(x).strip()})
    rows = []
    for idx in indexes:
        try:
            sc = compute_ai_score(idx, cfg=cfg, force=force)
            rows.append(
                {
                    "tracked_index": idx,
                    "pe_percentile": sc.components.get("pe_percentile"),
                    "pb_percentile": sc.components.get("pb_percentile"),
                    "ai_score": sc.total,
                }
            )
        except Exception:
            # 尝试别名：创业板指 → 创业板50
            alt = {"创业板指": "创业板50", "中证红利": "上证红利"}.get(idx)
            if not alt:
                continue
            try:
                sc = compute_ai_score(alt, cfg=cfg, force=force)
                rows.append(
                    {
                        "tracked_index": idx,
                        "pe_percentile": sc.components.get("pe_percentile"),
                        "pb_percentile": sc.components.get("pb_percentile"),
                        "ai_score": sc.total,
                    }
                )
            except Exception:
                continue
    if not rows:
        df = df.copy()
        df["pe_percentile"] = None
        df["pb_percentile"] = None
        df["ai_score"] = None
        return df
    meta = pd.DataFrame(rows)
    return df.merge(meta, on="tracked_index", how="left")


def screen_index_funds(cfg: dict[str, Any] | None = None, force: bool = False) -> pd.DataFrame:
    """按配置筛选指数基金。"""
    cfg = cfg or load_config()
    sc = cfg.get("screen", {})
    df = fetch_index_fund_table(cfg=cfg, force=force)
    if df.empty:
        return df

    # 数值列规范化
    for col in [
        "purchase_fee",
        "scale_yi",
        "total_fee",
        "mgmt_fee",
        "ret_1w",
        "ret_1m",
        "ret_3m",
        "ret_6m",
        "ret_1y",
        "ret_2y",
        "ret_3y",
        "ret_ytd",
        "nav",
    ]:
        if col in df.columns:
            df[col] = _to_num(df[col])

    mask = pd.Series(True, index=df.index)

    keywords = sc.get("index_keywords") or []
    if keywords:
        kw_mask = pd.Series(False, index=df.index)
        for kw in keywords:
            kw_mask |= df["name"].str.contains(str(kw), na=False)
            if "tracked_index" in df.columns:
                kw_mask |= df["tracked_index"].str.contains(str(kw), na=False)
        mask &= kw_mask

    name_contains = sc.get("name_contains") or []
    for kw in name_contains:
        mask &= df["name"].str.contains(str(kw), na=False)

    subtypes = sc.get("subtype_keywords") or []
    if subtypes:
        sub_mask = pd.Series(False, index=df.index)
        for kw in subtypes:
            sub_mask |= df["name"].str.contains(str(kw), na=False)
            if "subtype" in df.columns:
                sub_mask |= df["subtype"].str.contains(str(kw), na=False)
        mask &= sub_mask

    for kw in sc.get("exclude_keywords") or []:
        mask &= ~df["name"].str.contains(str(kw), na=False)

    mask &= _match_share_class(
        df.get("share_class", pd.Series("OTHER", index=df.index)),
        sc.get("share_class", "ALL"),
    )
    mask &= _match_subtype(df, sc.get("subtype_mode", "all"))

    min_scale = sc.get("min_scale_yi")
    if min_scale is not None and "scale_yi" in df.columns and df["scale_yi"].notna().any():
        mask &= df["scale_yi"].isna() | (df["scale_yi"] >= float(min_scale))

    max_scale = sc.get("max_scale_yi")
    if max_scale is not None and "scale_yi" in df.columns and df["scale_yi"].notna().any():
        mask &= df["scale_yi"].isna() | (df["scale_yi"] <= float(max_scale))

    max_purchase = sc.get("max_purchase_fee")
    if max_purchase is not None and "purchase_fee" in df.columns:
        mask &= df["purchase_fee"].isna() | (df["purchase_fee"] <= float(max_purchase))

    max_fee = sc.get("max_total_fee")
    if max_fee is not None and "total_fee" in df.columns and df["total_fee"].notna().any():
        mask &= df["total_fee"].isna() | (df["total_fee"] <= float(max_fee))

    # 收益区间
    for col, key_min, key_max in [
        ("ret_ytd", "min_ret_ytd", "max_ret_ytd"),
        ("ret_1y", "min_ret_1y", "max_ret_1y"),
        ("ret_3y", "min_ret_3y", "max_ret_3y"),
    ]:
        if col not in df.columns:
            continue
        lo = sc.get(key_min)
        hi = sc.get(key_max)
        s = df[col]
        if lo is not None:
            mask &= s.isna() | (s >= float(lo))
        if hi is not None:
            mask &= s.isna() | (s <= float(hi))

    out = df.loc[mask].copy()
    if out.empty:
        return out

    # 挂载指数估值 / AI 分，并按百分位过滤（规划：PE/PB 百分位筛选）
    need_val = any(
        sc.get(k) is not None
        for k in ("max_pe_percentile", "min_pe_percentile", "max_pb_percentile", "min_pb_percentile")
    ) or sc.get("attach_index_metrics", False)
    if need_val:
        # 先对候选跟踪指数去重计算，避免全表过慢：仅当前 out
        out = _attach_index_metrics(out, cfg, force=False)
        for col, key_min, key_max in [
            ("pe_percentile", "min_pe_percentile", "max_pe_percentile"),
            ("pb_percentile", "min_pb_percentile", "max_pb_percentile"),
        ]:
            if col not in out.columns:
                continue
            lo, hi = sc.get(key_min), sc.get(key_max)
            s = pd.to_numeric(out[col], errors="coerce")
            if lo is not None:
                out = out[s.isna() | (s >= float(lo))]
            if hi is not None:
                out = out[s.isna() | (s <= float(hi))]
        if out.empty:
            return out

    if sc.get("rule_4433"):
        out = out.loc[_apply_4433(out)].copy()
        if out.empty:
            return out

    out["score"] = _score_funds(out)

    top_n = int(sc.get("top_n") or 30)
    sort_by = sc.get("sort_by") or "score_desc"

    sort_map = {
        "name": ("name", True),
        "scale_desc": ("scale_yi", False),
        "fee_asc": ("purchase_fee", True),
        "ret_1y_desc": ("ret_1y", False),
        "ret_3y_desc": ("ret_3y", False),
        "score_desc": ("score", False),
    }
    col, asc = sort_map.get(sort_by, ("score", False))
    if col == "purchase_fee" and "total_fee" in out.columns and out["total_fee"].notna().any():
        # 有综合费率时优先用综合费率
        out = out.sort_values(
            by=["total_fee", "purchase_fee"],
            ascending=[True, True],
            na_position="last",
        )
    elif col in out.columns:
        out = out.sort_values(col, ascending=asc, na_position="last")
    else:
        out = out.sort_values("code")

    candidates = out.head(max(top_n * 2, top_n)).copy()
    if sc.get("enrich_fees"):
        try:
            fees = enrich_fund_fees(candidates["code"].head(top_n).tolist(), cfg=cfg)
            if not fees.empty:
                drop_cols = [
                    c
                    for c in ["scale_yi", "mgmt_fee", "custodian_fee", "total_fee"]
                    if c in candidates.columns
                ]
                candidates = candidates.drop(columns=drop_cols, errors="ignore")
                candidates = candidates.merge(fees, on="code", how="left")
                candidates["score"] = _score_funds(candidates)
        except Exception:
            pass

    # 补全后再应用规模/综合费率
    if min_scale is not None and "scale_yi" in candidates.columns:
        known = candidates["scale_yi"].notna()
        candidates = candidates[~known | (candidates["scale_yi"] >= float(min_scale))]
    if max_fee is not None and "total_fee" in candidates.columns:
        known = candidates["total_fee"].notna()
        candidates = candidates[~known | (candidates["total_fee"] <= float(max_fee))]

    if col == "purchase_fee" and "total_fee" in candidates.columns and candidates["total_fee"].notna().any():
        candidates = candidates.sort_values(
            by=["total_fee", "purchase_fee"], ascending=[True, True], na_position="last"
        )
    elif col in candidates.columns:
        candidates = candidates.sort_values(col, ascending=asc, na_position="last")

    keep = [c for c, _ in DISPLAY_COLUMNS if c in candidates.columns]
    result = candidates[keep].head(top_n).reset_index(drop=True)
    return result


def to_display(df: pd.DataFrame) -> pd.DataFrame:
    """中文列名，便于界面展示。"""
    if df is None or df.empty:
        return df
    rename = {c: zh for c, zh in DISPLAY_COLUMNS if c in df.columns}
    out = df.rename(columns=rename).copy()
    for col in ["规模(亿)", "申购费%", "综合费率%", "净值", "今年来%", "近1年%", "近2年%", "近3年%", "综合分", "PE百分位", "PB百分位", "AI分"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(2)
    return out
