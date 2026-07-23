"""强制给网络库加上默认超时，避免 akshare 无限挂起。"""
from __future__ import annotations

_PATCHED = False
_TIMEOUT = 12.0


def install_requests_timeout(timeout: float = 12.0) -> None:
    """给 requests / urllib 设置默认超时。

    akshare 常显式传 ``timeout=None``（永不超时），``setdefault`` 无效，
    必须把 ``None`` 也改写成具体秒数。部分接口走 urllib，需一并打补丁。
    """
    global _PATCHED, _TIMEOUT
    _TIMEOUT = float(timeout)
    if _PATCHED:
        return
    _patch_requests(_TIMEOUT)
    _patch_urllib(_TIMEOUT)
    _PATCHED = True


def _patch_requests(timeout: float) -> None:
    try:
        from requests.sessions import Session
    except Exception:
        return

    original = Session.request

    def request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = timeout
        return original(self, method, url, **kwargs)

    Session.request = request  # type: ignore[method-assign]


def _patch_urllib(timeout: float) -> None:
    try:
        import urllib.request as urllib_request
    except Exception:
        return

    original = urllib_request.urlopen

    def urlopen(url, data=None, timeout=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        if timeout is None:
            timeout = _TIMEOUT
        return original(url, data=data, timeout=timeout, *args, **kwargs)

    urllib_request.urlopen = urlopen  # type: ignore[assignment]
