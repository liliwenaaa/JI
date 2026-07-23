"""后台加载任务：可取消、可软超时，避免 UI 永久等待。"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

ProgressCb = Callable[[int, int, str], None]
LoadFn = Callable[[ProgressCb], dict[str, Any]]


@dataclass
class BgJob:
    id: str
    kind: str
    generation: int = 0
    status: str = "running"  # running | done | error | cancelled
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    done: int = 0
    total: int = 1
    message: str = "准备中"
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    soft_timeout_sec: float = 60.0
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def report(self, done: int, total: int, msg: str = "") -> None:
        if self._cancel.is_set():
            return
        with self._lock:
            self.done = int(done)
            self.total = max(int(total), 1)
            self.message = str(msg or "")

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self, reason: str = "已取消") -> None:
        self._cancel.set()
        with self._lock:
            if self.status == "running":
                self.status = "cancelled"
                self.error = reason
                self.finished_at = time.monotonic()

    def mark_soft_timeout(self) -> None:
        """UI 侧软超时：立刻结束等待，后台线程可继续但结果会被丢弃。"""
        self._cancel.set()
        with self._lock:
            if self.status == "running":
                # 若已有部分结果，尽量带出去
                self.status = "error" if not self.result else "done"
                if self.status == "error":
                    self.error = f"加载超时（>{self.soft_timeout_sec:.0f}s），已停止等待"
                self.message = "超时结束"
                self.finished_at = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "kind": self.kind,
                "generation": self.generation,
                "status": self.status,
                "error": self.error,
                "done": self.done,
                "total": self.total,
                "message": self.message,
                "elapsed": time.monotonic() - self.started_at,
                "soft_timeout_sec": self.soft_timeout_sec,
            }


_JOBS: dict[str, BgJob] = {}
_JOBS_LOCK = threading.Lock()
_GENERATION = 0
_GENERATION_LOCK = threading.Lock()


def bump_generation() -> int:
    """换页时递增，过期任务结果不再写入 session。"""
    global _GENERATION
    with _GENERATION_LOCK:
        _GENERATION += 1
        return _GENERATION


def current_generation() -> int:
    with _GENERATION_LOCK:
        return _GENERATION


def start_bg_job(
    kind: str,
    fn: LoadFn,
    *,
    soft_timeout_sec: float = 60.0,
    hard_timeout_sec: float = 90.0,
    generation: int | None = None,
) -> BgJob:
    """启动后台加载；fn 勿触碰 streamlit。"""
    gen = current_generation() if generation is None else int(generation)
    job = BgJob(
        id=uuid.uuid4().hex[:12],
        kind=kind,
        generation=gen,
        soft_timeout_sec=float(soft_timeout_sec),
    )
    with _JOBS_LOCK:
        _JOBS[job.id] = job

    def _runner() -> None:
        def progress(done: int, total: int, msg: str = "") -> None:
            if job.cancelled():
                raise InterruptedError("cancelled")
            job.report(done, total, msg)

        try:
            result = fn(progress)
            with job._lock:
                if job.status not in {"running"}:
                    return
                if job.generation != current_generation():
                    job.status = "cancelled"
                    job.error = "页面已切换"
                    job.finished_at = time.monotonic()
                    return
                job.result = dict(result or {})
                job.status = "done"
                job.finished_at = time.monotonic()
                job.done = max(job.done, job.total)
                if not job.message or job.message == "准备中":
                    job.message = "完成"
        except InterruptedError:
            with job._lock:
                if job.status == "running":
                    job.status = "cancelled"
                    job.error = "已取消"
                    job.finished_at = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            with job._lock:
                if job.status == "running":
                    job.error = str(exc)
                    job.status = "error"
                    job.finished_at = time.monotonic()

    threading.Thread(target=_runner, name=f"ji-bg-{kind}", daemon=True).start()

    def _watchdog() -> None:
        time.sleep(max(float(soft_timeout_sec), float(hard_timeout_sec)))
        with job._lock:
            if job.status == "running":
                job.status = "error"
                job.error = f"加载超时（>{hard_timeout_sec:.0f}s）"
                job.finished_at = time.monotonic()
                job._cancel.set()

    threading.Thread(target=_watchdog, name=f"ji-bg-wd-{kind}", daemon=True).start()
    return job


def get_bg_job(job_id: str | None) -> BgJob | None:
    if not job_id:
        return None
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def drop_bg_job(job_id: str | None) -> None:
    if not job_id:
        return
    with _JOBS_LOCK:
        job = _JOBS.pop(job_id, None)
    if job is not None:
        job.cancel("已丢弃")
