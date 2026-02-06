from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from datam8.core.errors import (
    Datam8NotFoundError,
    Datam8NotImplementedError,
    Datam8ValidationError,
)
from datam8.core.jobs.models import Job, JobError, JobEvent


def _now_ms() -> int:
    return int(time.time() * 1000)


def _job_id() -> str:
    return uuid.uuid4().hex


def _kill_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            return
        return

    try:
        os.killpg(pid, signal.SIGTERM)  # type: ignore[arg-type]
        return
    except Exception:
        pass
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return


@dataclass(frozen=True)
class _Subscriber:
    queue: asyncio.Queue[JobEvent]


class JobManager:
    def __init__(
        self,
        *,
        max_concurrency: int = 2,
        max_jobs: int = 50,
        job_ttl_seconds: int = 60 * 60,
        event_buffer_size: int = 500,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._max_concurrency = max_concurrency
        self._max_jobs = max_jobs
        self._job_ttl_ms = int(job_ttl_seconds * 1000)
        self._event_buffer_size = event_buffer_size

        self._jobs: dict[str, Job] = {}
        self._events: dict[str, deque[JobEvent]] = {}
        self._subs: dict[str, set[_Subscriber]] = {}
        self._procs: dict[str, asyncio.subprocess.Process] = {}

        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._started = False

        self._handlers: dict[str, Callable[[Job], Awaitable[Any]]] = {
            "generate": self._run_generate,
            "index": self._run_index,
            "validate": self._run_validate,
            "pluginVerify": self._run_plugin_verify,
        }

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for i in range(self._max_concurrency):
            self._workers.append(asyncio.create_task(self._worker(i)))

    async def stop(self) -> None:
        for t in self._workers:
            t.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._started = False

    def create_job(self, *, type: str, params: dict[str, Any]) -> Job:
        if type not in self._handlers:
            raise Datam8NotImplementedError(message=f"Job type '{type}' is not implemented.", details={"type": type})

        self._cleanup()
        jid = _job_id()
        job = Job(id=jid, type=type, params=params, status="queued", created_at_ms=_now_ms())
        self._jobs[jid] = job
        self._events[jid] = deque(maxlen=self._event_buffer_size)
        self._subs[jid] = set()
        self._emit(jid, "status", {"status": job.status})
        self._queue.put_nowait(jid)
        return job

    def get_job(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if not job:
            raise Datam8NotFoundError(message="Job not found.", details={"jobId": job_id})
        return job

    def cancel_job(self, job_id: str) -> Job:
        job = self.get_job(job_id)
        if job.status in {"succeeded", "failed", "canceled"}:
            return job
        if job.status == "queued":
            job.canceled = True
            job.status = "canceled"
            job.finished_at_ms = _now_ms()
            job.progress = None
            self._emit(job_id, "status", {"status": job.status})
            return job
        job.canceled = True
        self._emit(job_id, "status", {"status": job.status, "canceled": True})

        proc = self._procs.get(job_id)
        if proc and proc.pid:
            _kill_process_tree(proc.pid)
        return job

    async def subscribe(self, job_id: str) -> AsyncIterator[JobEvent]:
        q, initial, close = self.open_subscription(job_id)
        try:
            for ev in initial:
                yield ev
            while True:
                yield await q.get()
        finally:
            close()

    def open_subscription(self, job_id: str) -> tuple[asyncio.Queue[JobEvent], list[JobEvent], Callable[[], None]]:
        _ = self.get_job(job_id)
        q: asyncio.Queue[JobEvent] = asyncio.Queue()
        sub = _Subscriber(queue=q)
        self._subs[job_id].add(sub)
        initial = list(self._events.get(job_id, []))

        def close() -> None:
            self._subs.get(job_id, set()).discard(sub)

        return q, initial, close

    def _emit(self, job_id: str, event_type: str, data: dict[str, Any]) -> None:
        ev = JobEvent(type=event_type, data=data, ts_ms=_now_ms())  # type: ignore[arg-type]
        buf = self._events.get(job_id)
        if buf is not None:
            buf.append(ev)
        for sub in list(self._subs.get(job_id, set())):
            try:
                sub.queue.put_nowait(ev)
            except Exception:
                continue

    async def _worker(self, idx: int) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if not job:
                continue
            if job.canceled:
                job.status = "canceled"
                job.finished_at_ms = _now_ms()
                self._emit(job_id, "status", {"status": job.status})
                continue

            job.status = "running"
            job.started_at_ms = _now_ms()
            job.progress = 0.0
            self._emit(job_id, "status", {"status": job.status})
            self._emit(job_id, "progress", {"progress": 0.0})

            try:
                handler = self._handlers[job.type]
                result = await handler(job)
                if job.canceled:
                    job.status = "canceled"
                    job.finished_at_ms = _now_ms()
                    job.progress = None
                    self._emit(job_id, "status", {"status": job.status})
                else:
                    job.status = "succeeded"
                    job.finished_at_ms = _now_ms()
                    job.progress = 1.0
                    job.result = result
                    self._emit(job_id, "progress", {"progress": 1.0})
                    self._emit(job_id, "result", {"result": result})
                    self._emit(job_id, "status", {"status": job.status})
            except Exception as e:
                job.status = "failed"
                job.finished_at_ms = _now_ms()
                job.progress = None
                job.error = JobError(code="job_failed", message=str(e) or "Job failed.", details=None)
                self._emit(job_id, "error", {"error": {"code": job.error.code, "message": job.error.message, "details": job.error.details}})
                self._emit(job_id, "status", {"status": job.status})
            finally:
                self._procs.pop(job_id, None)

    def _cleanup(self) -> None:
        # TTL cleanup
        cutoff = _now_ms() - self._job_ttl_ms
        remove: list[str] = []
        for jid, job in self._jobs.items():
            if job.status in {"queued", "running"}:
                continue
            if (job.finished_at_ms or job.created_at_ms) < cutoff:
                remove.append(jid)
        for jid in remove:
            self._jobs.pop(jid, None)
            self._events.pop(jid, None)
            self._subs.pop(jid, None)
            self._procs.pop(jid, None)

        # Keep last N jobs
        if len(self._jobs) <= self._max_jobs:
            return
        ordered = sorted(self._jobs.values(), key=lambda j: j.created_at_ms, reverse=True)
        keep = {j.id for j in ordered[: self._max_jobs]}
        for jid in list(self._jobs.keys()):
            if jid not in keep:
                self._jobs.pop(jid, None)
                self._events.pop(jid, None)
                self._subs.pop(jid, None)
                self._procs.pop(jid, None)

    async def _run_generate(self, job: Job) -> dict[str, Any]:
        p = job.params or {}
        solution_path = p.get("solutionPath")
        target = p.get("target")
        if not isinstance(solution_path, str) or not solution_path.strip():
            raise Datam8ValidationError(message="params.solutionPath is required.", details=None)
        if not isinstance(target, str) or not target.strip():
            raise Datam8ValidationError(message="params.target is required.", details=None)

        if getattr(sys, "frozen", False):
            argv = [sys.executable, "generate", "--solution-path", solution_path, target]
        else:
            argv = [sys.executable, "-m", "datam8", "generate", "--solution-path", solution_path, target]
        log_level = p.get("logLevel")
        if isinstance(log_level, str) and log_level.strip():
            argv += ["--log-level", log_level.strip()]
        if bool(p.get("cleanOutput")):
            argv.append("--clean-output")
        payloads = p.get("payloads")
        if isinstance(payloads, list):
            for pl in payloads:
                if isinstance(pl, str) and pl.strip():
                    argv += ["--payload", pl.strip()]

        self._emit(job.id, "log", {"stream": "stderr", "message": f"$ {' '.join(argv)}"})

        creationflags = 0
        start_new_session = False
        if sys.platform != "win32":
            start_new_session = True
        else:
            try:
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            except Exception:
                creationflags = 0

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=start_new_session,
            creationflags=creationflags,
        )
        self._procs[job.id] = proc

        async def pump(stream, name: str) -> None:
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    break
                msg = line.decode("utf-8", errors="replace").rstrip("\r\n")
                job.logs.append(msg)
                self._emit(job.id, "log", {"stream": name, "message": msg})

        await asyncio.gather(pump(proc.stdout, "stdout"), pump(proc.stderr, "stderr"))

        rc = await proc.wait()
        if job.canceled:
            return {"exitCode": rc, "canceled": True}
        if rc != 0:
            raise RuntimeError(f"Generator exited with code {rc}.")
        return {"exitCode": rc}

    async def _run_index(self, job: Job) -> dict[str, Any]:
        from datam8.core.workspace_io import regenerate_index

        solution_path = job.params.get("solutionPath")
        if not isinstance(solution_path, str) or not solution_path.strip():
            raise Datam8ValidationError(message="params.solutionPath is required.", details=None)
        idx = regenerate_index(solution_path)
        return {"index": idx}

    async def _run_validate(self, job: Job) -> dict[str, Any]:
        from datam8.core.indexing import validate_index

        solution_path = job.params.get("solutionPath")
        report = validate_index(solution_path if isinstance(solution_path, str) else None)
        return {"report": report}

    async def _run_plugin_verify(self, job: Job) -> dict[str, Any]:
        from datam8.core.connectors.plugin_manager import default_plugin_dir
        from datam8.core.connectors.plugin_manager import reload as reload_plugins

        plugin_dir_raw = job.params.get("pluginDir")
        plugin_dir = default_plugin_dir()
        if isinstance(plugin_dir_raw, str) and plugin_dir_raw.strip():
            plugin_dir = __import__("pathlib").Path(plugin_dir_raw)
        state = reload_plugins(plugin_dir)
        return {"pluginDir": str(plugin_dir), "state": state}

    def to_public_job(self, job: Job) -> dict[str, Any]:
        return {
            "jobId": job.id,
            "type": job.type,
            "params": job.params,
            "status": job.status,
            "createdAt": job.created_at_ms,
            "startedAt": job.started_at_ms,
            "finishedAt": job.finished_at_ms,
            "progress": job.progress,
            "result": job.result,
            "error": None if not job.error else {"code": job.error.code, "message": job.error.message, "details": job.error.details},
        }

    @staticmethod
    def format_sse(ev: JobEvent) -> str:
        payload = json.dumps({"type": ev.type, "ts": ev.ts_ms, **ev.data}, separators=(",", ":"))
        return f"event: {ev.type}\ndata: {payload}\n\n"
