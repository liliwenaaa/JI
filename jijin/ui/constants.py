from __future__ import annotations

from jijin.data.market import INDEX_GROUPS, INDEX_SYMBOLS

INDEX_OPTIONS = list(INDEX_SYMBOLS.keys())
INDEX_GROUP_OPTIONS = ["全部", *INDEX_GROUPS.keys()]


def score_cache_key(pick: list[str], horizon: str) -> tuple[str, str]:
    """顺序无关，避免 multiselect 顺序变化导致算完又被当成未命中缓存。"""
    return ("|".join(sorted(str(x) for x in pick)), str(horizon))
