from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from jijin.config import cache_dir, load_config
from jijin.data.cache import CacheStore


# 乐咕乐股 stock_index_pe_lg / pb_lg 支持的 symbol
LEGULEGU_INDEXES: list[str] = [
    "上证50",
    "沪深300",
    "上证380",
    "创业板50",
    "中证500",
    "上证180",
    "深证红利",
    "深证100",
    "中证1000",
    "上证红利",
    "中证100",
    "中证800",
]

# 用户常用名 → 乐咕 symbol
INDEX_ALIASES: dict[str, list[str]] = {
    "沪深300": ["沪深300", "HS300"],
    "中证500": ["中证500", "ZZ500"],
    "中证1000": ["中证1000", "ZZ1000"],
    "上证50": ["上证50"],
    "中证100": ["中证100"],
    "中证800": ["中证800"],
    "创业板50": ["创业板50", "创业板指", "创业板", "创业板指数"],
    "上证红利": ["上证红利", "红利", "中证红利"],
    "深证红利": ["深证红利"],
}


@dataclass
class IndexValuation:
    index_name: str
    matched_name: str
    date: str | None
    pe: float | None
    pe_percentile: float | None
    pb: float | None
    pb_percentile: float | None
    raw: dict[str, Any]


def _store(cfg: dict[str, Any]) -> CacheStore:
    return CacheStore(cache_dir(cfg) / "jijin_cache.db")


def _percentile(series: pd.Series, value: float) -> float | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty or value is None or pd.isna(value):
        return None
    return float((s <= value).mean() * 100)


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    # 模糊
    for col in df.columns:
        for c in candidates:
            if c in str(col):
                return col
    return None


def list_pe_indexes(cfg: dict[str, Any] | None = None, force: bool = False) -> list[str]:
    _ = cfg, force
    return list(LEGULEGU_INDEXES)


def _resolve_index_name(query: str, available: list[str]) -> str | None:
    q = (query or "").strip()
    if not q:
        return None
    if q in available:
        return q
    # 别名表：用户输入 → 官方 symbol
    for canonical, aliases in INDEX_ALIASES.items():
        if q == canonical or q in aliases:
            if canonical in available:
                return canonical
    # 模糊包含
    for name in available:
        if q in name or name in q:
            return name
    for canonical, aliases in INDEX_ALIASES.items():
        for a in aliases:
            if q in a or a in q:
                if canonical in available:
                    return canonical
    return None


def fetch_index_valuation(
    index_name: str,
    cfg: dict[str, Any] | None = None,
    force: bool = False,
) -> IndexValuation:
    """获取指数最新 PE/PB 及历史百分位。"""
    cfg = cfg or load_config()
    store = _store(cfg)
    ttl = float(cfg.get("cache", {}).get("valuation_ttl_hours", 6))
    cache_key = f"index_val:{index_name}"

    if not force:
        cached = store.get(cache_key, ttl)
        if cached is not None:
            return IndexValuation(**cached)

    import time

    import akshare as ak

    from jijin.utils.timeout import call_with_timeout

    available = list_pe_indexes(cfg, force=False)
    matched = _resolve_index_name(index_name, available) or index_name

    pe_df = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            pe_df = call_with_timeout(ak.stock_index_pe_lg, 20, symbol=matched)
            if pe_df is not None and not pe_df.empty:
                break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.4 * (attempt + 1))
    if pe_df is None or pe_df.empty:
        # 远端失败时回退过期缓存
        stale = store.get(cache_key, ttl_hours=24 * 30)
        if stale is not None:
            return IndexValuation(**stale)
        raise RuntimeError(f"获取 {matched} 估值失败: {last_err}")

    pb_df = None
    try:
        pb_df = call_with_timeout(ak.stock_index_pb_lg, 15, symbol=matched)
    except Exception:
        pb_df = None

    date_col = _pick_column(pe_df, ["日期", "date"])
    # 优先滚动市盈率（TTM）
    pe_col = _pick_column(pe_df, ["滚动市盈率", "等权滚动市盈率", "静态市盈率", "市盈率", "pe", "PE"])

    pe = None
    pe_pct = None
    date = None
    if pe_df is not None and not pe_df.empty and pe_col:
        last = pe_df.iloc[-1]
        pe = float(pd.to_numeric(last[pe_col], errors="coerce"))
        date = str(last[date_col])[:10] if date_col else None
        pe_pct = _percentile(pe_df[pe_col], pe)

    pb = None
    pb_pct = None
    if pb_df is not None and not pb_df.empty:
        pb_col = _pick_column(pb_df, ["市净率", "等权市净率", "pb", "PB"])
        if pb_col:
            last_pb = pb_df.iloc[-1]
            pb = float(pd.to_numeric(last_pb[pb_col], errors="coerce"))
            pb_pct = _percentile(pb_df[pb_col], pb)

    result = IndexValuation(
        index_name=index_name,
        matched_name=matched,
        date=date,
        pe=pe,
        pe_percentile=pe_pct,
        pb=pb,
        pb_percentile=pb_pct,
        raw={},
    )
    store.set(
        cache_key,
        {
            "index_name": result.index_name,
            "matched_name": result.matched_name,
            "date": result.date,
            "pe": result.pe,
            "pe_percentile": result.pe_percentile,
            "pb": result.pb,
            "pb_percentile": result.pb_percentile,
            "raw": {},
        },
    )
    return result


def fetch_watch_valuations(cfg: dict[str, Any] | None = None, force: bool = False) -> list[IndexValuation]:
    cfg = cfg or load_config()
    names = cfg.get("valuation", {}).get("watch_indexes") or []
    out: list[IndexValuation] = []
    for name in names:
        try:
            out.append(fetch_index_valuation(name, cfg=cfg, force=force))
        except Exception as exc:  # noqa: BLE001 — 单指数失败不阻断
            out.append(
                IndexValuation(
                    index_name=name,
                    matched_name=name,
                    date=None,
                    pe=None,
                    pe_percentile=None,
                    pb=None,
                    pb_percentile=None,
                    raw={"error": str(exc)},
                )
            )
    return out
