from __future__ import annotations

import re
from typing import Any

import pandas as pd

from jijin.config import cache_dir, load_config
from jijin.data.cache import CacheStore


def _store(cfg: dict[str, Any] | None = None) -> CacheStore:
    cfg = cfg or load_config()
    return CacheStore(cache_dir(cfg) / "jijin_cache.db")


def _safe_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("%", "")
    if not s or s in {"--", "-", "nan", "None"}:
        return None
    # 处理「12.34亿」
    mult = 1.0
    if s.endswith("亿"):
        mult = 1.0
        s = s[:-1]
    elif s.endswith("万"):
        mult = 1e-4
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group()) * mult if m else None


def _share_class(name: str) -> str:
    n = name or ""
    # 优先识别独立份额字母，避免误伤「联接」等
    if re.search(r"(?<![A-Za-z])C(?![A-Za-z])|C类|C份额", n):
        return "C"
    if re.search(r"(?<![A-Za-z])A(?![A-Za-z])|A类|A份额", n):
        return "A"
    if "E" in n and "联接" in n:
        return "E"
    return "OTHER"


def _infer_subtype(name: str) -> str:
    n = name or ""
    if "增强" in n:
        return "指数增强"
    if "ETF联接" in n or "联接" in n:
        return "ETF联接"
    if "ETF" in n:
        return "ETF"
    return "被动指数"


def _load_index_fund_raw(ak: Any) -> pd.DataFrame:
    """尝试多个 AKShare 接口获取指数基金列表。"""
    errors: list[str] = []
    candidates = []
    if hasattr(ak, "fund_info_index_em"):
        candidates.append(("fund_info_index_em", lambda: ak.fund_info_index_em()))
    if hasattr(ak, "fund_open_fund_daily_em"):
        candidates.append(
            (
                "fund_open_fund_daily_em",
                lambda: ak.fund_open_fund_daily_em(),
            )
        )
    if hasattr(ak, "fund_name_em"):
        candidates.append(("fund_name_em", lambda: ak.fund_name_em()))

    for name, fn in candidates:
        try:
            df = fn()
            if df is None or df.empty:
                continue
            # fund_name_em / 全市场：尽量过滤指数相关
            name_col = next((c for c in df.columns if "简称" in str(c) or c in {"基金简称", "基金名称", "name"}), None)
            type_col = next((c for c in df.columns if "类型" in str(c)), None)
            if name == "fund_name_em" and (name_col or type_col):
                mask = pd.Series(False, index=df.index)
                if type_col:
                    mask |= df[type_col].astype(str).str.contains("指数", na=False)
                if name_col:
                    mask |= df[name_col].astype(str).str.contains("指数|ETF", na=False, regex=True)
                df = df.loc[mask].copy()
            if not df.empty:
                return df
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    raise RuntimeError("无法获取指数基金列表: " + " | ".join(errors[:3]))


def fetch_index_fund_table(cfg: dict[str, Any] | None = None, force: bool = False) -> pd.DataFrame:
    """拉取指数型基金列表并规范化字段。"""
    cfg = cfg or load_config()
    ttl = float(cfg.get("cache", {}).get("fund_list_ttl_hours", 24))
    store = _store(cfg)
    cache_key = "index_fund_list_v3"

    if not force:
        cached = store.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

    import akshare as ak

    df = _load_index_fund_raw(ak)
    # 常见列名兼容
    colmap = {
        "基金代码": "code",
        "基金简称": "name",
        "基金名称": "name",
        "单位净值": "nav",
        "日期": "nav_date",
        "日增长率": "day_chg",
        "近1周": "ret_1w",
        "近1月": "ret_1m",
        "近3月": "ret_3m",
        "近6月": "ret_6m",
        "近1年": "ret_1y",
        "近2年": "ret_2y",
        "近3年": "ret_3y",
        "今年来": "ret_ytd",
        "成立来": "ret_since",
        "手续费": "purchase_fee",
        "跟踪标的": "track_target",
        "跟踪方式": "track_method",
        "起购金额": "min_purchase",
    }
    rename = {k: v for k, v in colmap.items() if k in df.columns}
    out = df.rename(columns=rename).copy()

    if "code" not in out.columns:
        # 兜底：取第一列当代码
        out = out.rename(columns={out.columns[0]: "code", out.columns[1]: "name"})

    out["code"] = out["code"].astype(str).str.zfill(6)
    out["name"] = out["name"].astype(str)
    out["share_class"] = out["name"].map(_share_class)
    # 名称推断更细（增强 / 联接）；接口跟踪方式多为笼统「被动指数型」
    out["subtype"] = out["name"].map(_infer_subtype)
    if "track_method" in out.columns:
        # 名称未能细分时，回退接口字段
        coarse = out["subtype"].isin(["被动指数", "被动指数型"])
        tm = out["track_method"].fillna("").astype(str)
        use_tm = coarse & tm.ne("") & ~tm.isin(["nan", "None"])
        out.loc[use_tm, "subtype"] = tm[use_tm]

    # 尝试补充规模与管理/托管费率（批量可能较慢，做尽力而为）
    fee_scale = _fetch_fee_scale_batch(out["code"].tolist(), store, force=force)
    if not fee_scale.empty:
        out = out.merge(fee_scale, on="code", how="left")
    else:
        out["scale_yi"] = None
        out["mgmt_fee"] = None
        out["custodian_fee"] = None
        out["total_fee"] = None

    # 从名称推断跟踪指数（接口「跟踪标的」过粗，名称更准）
    out["tracked_index"] = out["name"].map(_guess_index_from_name)

    records = out.to_dict(orient="records")
    store.set(cache_key, records)
    return out


def _guess_index_from_name(name: str) -> str:
    n = name or ""
    rules = [
        ("沪深300", "沪深300"),
        ("上证50", "上证50"),
        ("中证500", "中证500"),
        ("中证1000", "中证1000"),
        ("中证100", "中证100"),
        ("中证800", "中证800"),
        ("创业板50", "创业板50"),
        ("创业板", "创业板指"),
        ("科创50", "科创50"),
        ("科创板", "科创50"),
        ("中证红利", "中证红利"),
        ("红利低波", "红利低波"),
        ("中证消费", "中证消费"),
        ("证券公司", "中证全指证券公司"),
        ("银行", "中证银行"),
        ("医药", "中证医药"),
        ("军工", "中证军工"),
        ("新能源", "中证新能源"),
        ("半导体", "国证半导体"),
        ("纳斯达克", "纳斯达克100"),
        ("标普500", "标普500"),
        ("恒生科技", "恒生科技"),
        ("恒生", "恒生指数"),
    ]
    for kw, idx in rules:
        if kw in n:
            return idx
    return ""


def _fetch_fee_scale_batch(codes: list[str], store: CacheStore, force: bool = False) -> pd.DataFrame:
    """尽力补充规模与费率；失败则返回空表。

    说明：全量逐只请求过慢，这里优先用东方财富指数基金表已有字段；
    若后续接口可用再扩展。当前通过 ak.fund_fee_em 等不稳定接口时做静默降级。
    """
    cache_key = "fee_scale_partial_v2"
    if not force:
        cached = store.get(cache_key, ttl_hours=24)
        if cached is not None:
            return pd.DataFrame(cached)

    # 首版：不阻塞主流程，返回空；筛选时用名称+已有收益字段即可
    # 用户可后续 refresh 扩展
    try:
        import akshare as ak

        # 部分版本提供开放式基金实时规模排行，可 join
        if hasattr(ak, "fund_scale_open_sina"):
            scale_df = ak.fund_scale_open_sina()
            code_col = next((c for c in scale_df.columns if "代码" in str(c)), None)
            # 优先「总募集规模」（多为万元），避免误用「最近总份额」
            scale_col = next(
                (c for c in ["总募集规模", "基金规模", "规模"] if c in scale_df.columns),
                next((c for c in scale_df.columns if "规模" in str(c) and "份额" not in str(c)), None),
            )
            if code_col and scale_col:
                raw = scale_df[scale_col].map(_safe_float)
                # 新浪「总募集规模」常见单位为万元 → 转为亿元
                median = float(raw.dropna().median()) if raw.notna().any() else 0
                scale_yi = raw / 10000.0 if median > 500 else raw
                tmp = pd.DataFrame(
                    {
                        "code": scale_df[code_col].astype(str).str.zfill(6),
                        "scale_yi": scale_yi,
                    }
                )
                code_set = set(codes)
                tmp = tmp[tmp["code"].isin(code_set)].copy()
                tmp["mgmt_fee"] = None
                tmp["custodian_fee"] = None
                tmp["total_fee"] = None
                store.set(cache_key, tmp.to_dict(orient="records"))
                return tmp
    except Exception:
        pass
    return pd.DataFrame()


def enrich_fund_fees(codes: list[str], cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """对少量代码拉取详情费率（用于精选结果二次补全）。"""
    cfg = cfg or load_config()
    store = _store(cfg)
    rows: list[dict[str, Any]] = []

    import akshare as ak

    for code in codes:
        key = f"fund_detail:{code}"
        cached = store.get(key, ttl_hours=24 * 7)
        if cached is not None:
            rows.append(cached)
            continue
        item: dict[str, Any] = {
            "code": code,
            "scale_yi": None,
            "mgmt_fee": None,
            "custodian_fee": None,
            "total_fee": None,
        }
        try:
            if hasattr(ak, "fund_individual_basic_info_xq"):
                info = ak.fund_individual_basic_info_xq(symbol=code)
                # 雪球接口返回键值表
                if isinstance(info, pd.DataFrame) and not info.empty:
                    kv = {}
                    if {"item", "value"}.issubset(info.columns):
                        kv = dict(zip(info["item"], info["value"]))
                    elif info.shape[1] >= 2:
                        kv = dict(zip(info.iloc[:, 0], info.iloc[:, 1]))
                    item["mgmt_fee"] = _safe_float(kv.get("管理费率") or kv.get("管理费"))
                    item["custodian_fee"] = _safe_float(kv.get("托管费率") or kv.get("托管费"))
                    item["scale_yi"] = _safe_float(kv.get("基金规模") or kv.get("规模"))
            if item["mgmt_fee"] is not None or item["custodian_fee"] is not None:
                mg = item["mgmt_fee"] or 0.0
                cu = item["custodian_fee"] or 0.0
                item["total_fee"] = round(mg + cu, 4)
        except Exception:
            pass
        store.set(key, item)
        rows.append(item)
    return pd.DataFrame(rows)
