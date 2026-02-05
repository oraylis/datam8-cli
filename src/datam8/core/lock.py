from __future__ import annotations

import os
import time
from contextlib import AbstractContextManager
from pathlib import Path

from datam8.core.errors import Datam8ConflictError


class SolutionLock(AbstractContextManager["SolutionLock"]):
    def __init__(self, lock_file: Path, *, timeout_seconds: float = 10.0) -> None:
        self.lock_file = lock_file
        self.timeout_seconds = timeout_seconds
        self._fh = None

    def __enter__(self) -> SolutionLock:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_file, "a+b")
        self._fh = fh

        deadline = time.time() + self.timeout_seconds
        while True:
            try:
                _lock_handle(fh)
                return self
            except BlockingIOError:
                if time.time() >= deadline:
                    raise Datam8ConflictError(
                        code="locked",
                        message="Solution is locked by another process.",
                        details={"lockFile": str(self.lock_file)},
                        hint="Wait and retry, or use --lock-timeout / --no-lock (dangerous).",
                    )
                time.sleep(0.1)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is None:
            return
        try:
            _unlock_handle(self._fh)
        finally:
            try:
                self._fh.close()
            finally:
                self._fh = None


def _lock_handle(fh) -> None:
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            raise BlockingIOError() from e
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_handle(fh) -> None:
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

