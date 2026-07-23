"""内置数据源插件（当前默认 akshare 实现）。"""
from __future__ import annotations

from jijin.data.fund import fetch_index_fund_table
from jijin.data.macro import (
    fetch_cpi_yearly,
    fetch_lpr,
    fetch_money_supply,
    fetch_pmi_yearly,
)
from jijin.data.market import fetch_index_daily
from jijin.data.valuation import fetch_index_valuation
from jijin.plugin.base import DataProviderSpec
from jijin.plugin.registry import PluginRegistry


def register(reg: PluginRegistry) -> None:
    providers = [
        DataProviderSpec("index_daily", "market", fetch_index_daily, "指数日线 OHLCV"),
        DataProviderSpec("index_valuation", "valuation", fetch_index_valuation, "指数 PE/PB"),
        DataProviderSpec("index_funds", "fund", fetch_index_fund_table, "指数基金列表"),
        DataProviderSpec("macro_pmi", "macro", fetch_pmi_yearly, "PMI"),
        DataProviderSpec("macro_cpi", "macro", fetch_cpi_yearly, "CPI"),
        DataProviderSpec("macro_lpr", "macro", fetch_lpr, "LPR"),
        DataProviderSpec("macro_money", "macro", fetch_money_supply, "货币供应"),
    ]
    for spec in providers:
        reg.register_data_provider(spec, replace=True)
