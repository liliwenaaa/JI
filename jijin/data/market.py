from __future__ import annotations

from typing import Any

import pandas as pd

from jijin.config import cache_dir, load_config
from jijin.data.cache import CacheStore

# 指数名 → 行情 symbol（优先新浪；拉取失败时回退东方财富同代码）
# 选取有日线、常被 ETF/指数基金跟踪的宽基 + 行业/主题指数。
INDEX_SYMBOLS: dict[str, str] = {
    # —— 宽基 / 规模 ——
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "上证50": "sh000016",
    "上证180": "sh000010",
    "沪深300": "sh000300",
    "中证100": "sh000903",
    "中证500": "sh000905",
    "中证800": "sh000906",
    "中证1000": "sh000852",
    "深证100": "sz399330",
    "中小板指": "sz399005",
    "创业板指": "sz399006",
    "创业板50": "sz399673",
    "创业板综": "sz399102",
    "科创50": "sh000688",
    "科创100": "sh000698",
    "北证50": "bj899050",
    "微盘股": "sz399303",
    # —— 红利 / 风格 ——
    "上证红利": "sh000015",
    "深证红利": "sz399324",
    "中证红利": "sh000922",
    # —— 中证一级行业 ——
    "中证能源": "sh000928",
    "中证消费": "sh000932",
    "中证医药": "sh000933",
    "中证金融地产": "sh000934",
    "中证信息科技": "sh000935",
    # —— 金融地产细分 ——
    "国证银行": "sz399431",
    "证券公司": "sz399975",
    "中证保险": "sz399809",
    "中证地产": "sz399965",
    # —— 消费医药 ——
    "中证白酒": "sz399997",
    "中证食品饮料": "sh000807",
    "中证医疗": "sz399989",
    "中证生物": "sz399441",
    "沪深300医药": "sh000913",
    # —— 科技成长 ——
    "中证信息": "sh000993",
    "中证传媒": "sz399971",
    "中证通信": "sz399996",
    "半导体": "sz980017",
    "中证新能源": "sz399808",
    "新能源车": "sz399976",
    # —— 周期制造 ——
    "中证军工": "sz399967",
    "中证有色": "sz399395",
    "中证钢铁": "sz399440",
    "中证煤炭": "sz399998",
    "国证煤炭": "sz399436",
    "国证石油": "sz399439",
    "国证电力": "sz399438",
    "中证基建": "sz399995",
    "中证农业": "sz399265",
}

# 分组：用于界面筛选与说明（名称必须已在 INDEX_SYMBOLS）
INDEX_GROUPS: dict[str, list[str]] = {
    "宽基规模": [
        "上证指数",
        "深证成指",
        "上证50",
        "上证180",
        "沪深300",
        "中证100",
        "中证500",
        "中证800",
        "中证1000",
        "深证100",
        "中小板指",
        "创业板指",
        "创业板50",
        "创业板综",
        "科创50",
        "科创100",
        "北证50",
        "微盘股",
    ],
    "红利风格": ["上证红利", "深证红利", "中证红利"],
    "一级行业": ["中证能源", "中证消费", "中证医药", "中证金融地产", "中证信息科技"],
    "金融地产": ["国证银行", "证券公司", "中证保险", "中证地产"],
    "消费医药": ["中证白酒", "中证食品饮料", "中证医疗", "中证生物", "沪深300医药"],
    "科技成长": [
        "中证信息",
        "中证传媒",
        "中证通信",
        "半导体",
        "中证新能源",
        "新能源车",
    ],
    "周期制造": [
        "中证军工",
        "中证有色",
        "中证钢铁",
        "中证煤炭",
        "国证煤炭",
        "国证石油",
        "国证电力",
        "中证基建",
        "中证农业",
    ],
}


def _store(cfg: dict[str, Any]) -> CacheStore:
    return CacheStore(cache_dir(cfg) / "jijin_cache.db")


def list_index_names(*, group: str | None = None) -> list[str]:
    """返回指数名列表；可按 INDEX_GROUPS 分组过滤。"""
    if not group or group == "全部":
        return list(INDEX_SYMBOLS.keys())
    names = INDEX_GROUPS.get(group) or []
    return [n for n in names if n in INDEX_SYMBOLS]


def index_group_of(name: str) -> str:
    for group, names in INDEX_GROUPS.items():
        if name in names:
            return group
    return "其他"


def resolve_symbol(index_name: str) -> str | None:
    name = (index_name or "").strip()
    if name in INDEX_SYMBOLS:
        return INDEX_SYMBOLS[name]
    for k, v in INDEX_SYMBOLS.items():
        if k in name or name in k:
            return v
    return None


# 本地缓存最多保留约 6.5 年交易日，供策略校准截取。
_INDEX_DAILY_STORE_LIMIT = 1600


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "date" not in work.columns and "日期" in work.columns:
        work = work.rename(columns={"日期": "date"})
    for src, dst in {
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
    }.items():
        if dst not in work.columns and src in work.columns:
            work = work.rename(columns={src: dst})
    work["date"] = pd.to_datetime(work["date"])
    for c in ["open", "high", "low", "close", "volume"]:
        if c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce")
    return work.dropna(subset=["close"]).sort_values("date")


def _fetch_raw_daily(symbol: str):
    import akshare as ak

    # 1) 新浪
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is not None and not df.empty and "date" in df.columns:
            return _normalize_ohlcv(df)
    except Exception:
        pass

    # 2) 东方财富（同代码或 csi 前缀）
    candidates = [symbol]
    code = symbol[2:] if len(symbol) > 2 and symbol[:2] in {"sh", "sz", "bj"} else symbol
    if not symbol.startswith("csi"):
        candidates.append(f"csi{code}")
    for cand in candidates:
        try:
            df = ak.stock_zh_index_daily_em(symbol=cand)
            if df is not None and not df.empty:
                return _normalize_ohlcv(df)
        except Exception:
            continue
    return None


def fetch_index_daily(
    index_name: str,
    cfg: dict[str, Any] | None = None,
    force: bool = False,
    limit: int = 400,
) -> pd.DataFrame:
    """拉取指数日线（OHLCV）。

    缓存按完整长历史写入；`limit` 仅控制返回条数，避免校准要 5 年时
    仍命中仅含约 400 根 K 线的旧缓存。
    """
    cfg = cfg or load_config()
    symbol = resolve_symbol(index_name)
    if not symbol:
        raise ValueError(f"不支持的指数行情: {index_name}")

    store = _store(cfg)
    key = f"index_daily:{symbol}:v3"
    ttl = float(cfg.get("cache", {}).get("index_daily_ttl_hours", 12))
    want = max(1, int(limit))
    if not force:
        cached = store.get(key, ttl)
        if cached is not None:
            out = pd.DataFrame(cached)
            if "date" in out.columns:
                out["date"] = pd.to_datetime(out["date"])
            return out.tail(want).reset_index(drop=True)

    df = _fetch_raw_daily(symbol)
    if df is None or df.empty:
        raise RuntimeError(f"无行情数据: {symbol}")
    df = df.tail(_INDEX_DAILY_STORE_LIMIT)
    records = df.copy()
    records["date"] = records["date"].dt.strftime("%Y-%m-%d")
    store.set(key, records.to_dict(orient="records"))
    return df.tail(want).reset_index(drop=True)
