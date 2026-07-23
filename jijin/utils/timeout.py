from __future__ import annotations

import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

from jijin.utils.http_patch import install_requests_timeout

T = TypeVar("T")

# 进程启动即打补丁：akshare 走 requests 时不再无限等待
install_requests_timeout(12.0)

# 进程级默认超时（兜底非 requests 的阻塞）
_DEFAULT_SOCKET_TIMEOUT = 25.0
if socket.getdefaulttimeout() is None:
    socket.setdefaulttimeout(_DEFAULT_SOCKET_TIMEOUT)

# 共享线程池：避免每次 call_with_timeout 新建池 + 泄漏挂起线程把进程撑死
_TIMEOUT_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="ji-timeout")
_IN_TIMEOUT_WORKER = threading.local()


@contextmanager
def socket_timeout(seconds: float) -> Iterator[None]:
    """临时覆盖 socket 超时（尽量少用；优先依赖进程默认值与 requests patch）。"""
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(float(seconds))
    try:
        yield
    finally:
        socket.setdefaulttimeout(old)


def call_with_timeout(fn: Callable[..., T], timeout_sec: float, *args: Any, **kwargs: Any) -> T:
    """在共享线程池跑 fn，超时抛 TimeoutError。

    若当前已在超时池线程内，则直接同步执行，避免同池嵌套提交死锁。
    """
    if getattr(_IN_TIMEOUT_WORKER, "active", False):
        return fn(*args, **kwargs)

    def _runner() -> T:
        _IN_TIMEOUT_WORKER.active = True
        try:
            return fn(*args, **kwargs)
        finally:
            _IN_TIMEOUT_WORKER.active = False

    fut = _TIMEOUT_POOL.submit(_runner)
    try:
        return fut.result(timeout=float(timeout_sec))
    except FuturesTimeoutError as exc:
        raise TimeoutError(f"操作超时（>{timeout_sec:.0f}s）") from exc


def index_timeout_sec(cfg: dict[str, Any] | None = None, default: float = 20.0) -> float:
    """单个指数分析超时（秒），可在 config.cache.score_index_timeout_sec 覆盖。"""
    return float(((cfg or {}).get("cache") or {}).get("score_index_timeout_sec") or default)
