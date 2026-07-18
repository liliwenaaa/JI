from __future__ import annotations

from typing import Any

import pandas as pd

from jijin.config import cache_dir, load_config
from jijin.data.cache import CacheStore


def _store(cfg: dict[str, Any]) -> CacheStore:
    return CacheStore(cache_dir(cfg) / "jijin_cache.db")


def _ttl(cfg: dict[str, Any]) -> float:
    return float(cfg.get("cache", {}).get("macro_ttl_hours", 24))


def _cached_frame(
    key: str,
    fetcher,
    cfg: dict[str, Any],
    force: bool = False,
) -> pd.DataFrame:
    store = _store(cfg)
    if not force:
        cached = store.get(key, _ttl(cfg))
        if cached is not None:
            return pd.DataFrame(cached)

    df = fetcher()
    if df is None or df.empty:
        return pd.DataFrame()
    store.set(key, df.to_dict(orient="records"))
    return df


def _latest_numeric(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.iloc[-1])


def fetch_pmi_yearly(cfg: dict[str, Any] | None = None, force: bool = False) -> pd.DataFrame:
    import akshare as ak

    cfg = cfg or load_config()
    return _cached_frame("macro:pmi_yearly", ak.macro_china_pmi_yearly, cfg, force)


def fetch_cpi_yearly(cfg: dict[str, Any] | None = None, force: bool = False) -> pd.DataFrame:
    import akshare as ak

    cfg = cfg or load_config()
    return _cached_frame("macro:cpi_yearly", ak.macro_china_cpi_yearly, cfg, force)


def fetch_lpr(cfg: dict[str, Any] | None = None, force: bool = False) -> pd.DataFrame:
    import akshare as ak

    cfg = cfg or load_config()
    return _cached_frame("macro:lpr", ak.macro_china_lpr, cfg, force)


def fetch_money_supply(cfg: dict[str, Any] | None = None, force: bool = False) -> pd.DataFrame:
    import akshare as ak

    cfg = cfg or load_config()
    return _cached_frame("macro:money_supply", ak.macro_china_money_supply, cfg, force)


def latest_macro_raw(cfg: dict[str, Any] | None = None, force: bool = False) -> dict[str, Any]:
    """抓取并整理最新宏观原始值（失败时对应字段为 None）。"""
    cfg = cfg or load_config()
    out: dict[str, Any] = {
        "pmi": None,
        "pmi_prev": None,
        "pmi_date": None,
        "cpi": None,
        "cpi_prev": None,
        "cpi_date": None,
        "m2_yoy": None,
        "m1_yoy": None,
        "money_month": None,
        "lpr_1y": None,
        "lpr_5y": None,
        "lpr_date": None,
        "lpr_1y_prev": None,
        "errors": [],
    }

    try:
        pmi = fetch_pmi_yearly(cfg, force=force)
        if not pmi.empty and "今值" in pmi.columns:
            values = pd.to_numeric(pmi["今值"], errors="coerce").dropna()
            if not values.empty:
                out["pmi"] = float(values.iloc[-1])
                if len(values) >= 2:
                    out["pmi_prev"] = float(values.iloc[-2])
                if "日期" in pmi.columns:
                    out["pmi_date"] = str(pmi.loc[values.index[-1], "日期"])
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"pmi: {exc}")

    try:
        cpi = fetch_cpi_yearly(cfg, force=force)
        if not cpi.empty and "今值" in cpi.columns:
            values = pd.to_numeric(cpi["今值"], errors="coerce").dropna()
            if not values.empty:
                out["cpi"] = float(values.iloc[-1])
                if len(values) >= 2:
                    out["cpi_prev"] = float(values.iloc[-2])
                if "日期" in cpi.columns:
                    out["cpi_date"] = str(cpi.loc[values.index[-1], "日期"])
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"cpi: {exc}")

    try:
        money = fetch_money_supply(cfg, force=force)
        if not money.empty:
            # 接口按月份倒序返回
            m2_col = "货币和准货币(M2)-同比增长"
            m1_col = "货币(M1)-同比增长"
            if m2_col in money.columns:
                out["m2_yoy"] = _latest_numeric(money[m2_col].iloc[::-1])
                # 因倒序，首行即最新
                latest = pd.to_numeric(money[m2_col], errors="coerce")
                if latest.notna().any():
                    out["m2_yoy"] = float(latest.dropna().iloc[0])
            if m1_col in money.columns:
                latest_m1 = pd.to_numeric(money[m1_col], errors="coerce")
                if latest_m1.notna().any():
                    out["m1_yoy"] = float(latest_m1.dropna().iloc[0])
            if "月份" in money.columns:
                out["money_month"] = str(money["月份"].iloc[0])
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"money: {exc}")

    try:
        lpr = fetch_lpr(cfg, force=force)
        if not lpr.empty and "LPR1Y" in lpr.columns:
            lpr = lpr.copy()
            lpr["LPR1Y"] = pd.to_numeric(lpr["LPR1Y"], errors="coerce")
            valid = lpr.dropna(subset=["LPR1Y"])
            if not valid.empty:
                out["lpr_1y"] = float(valid["LPR1Y"].iloc[-1])
                if len(valid) >= 2:
                    out["lpr_1y_prev"] = float(valid["LPR1Y"].iloc[-2])
                if "LPR5Y" in valid.columns:
                    out["lpr_5y"] = float(pd.to_numeric(valid["LPR5Y"], errors="coerce").iloc[-1])
                if "TRADE_DATE" in valid.columns:
                    out["lpr_date"] = str(valid["TRADE_DATE"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"lpr: {exc}")

    return out
