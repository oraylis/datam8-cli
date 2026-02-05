from __future__ import annotations

import json
import sys
from typing import Any


def emit_human(msg: str) -> None:
    sys.stdout.write((msg or "") + "\n")
    sys.stdout.flush()


def emit_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_error_json(*, code: str, message: str, details: Any = None, hint: str | None = None, trace_id: str | None = None) -> None:
    emit_json({"status": "error", "code": code, "message": message, "details": details, "hint": hint, "traceId": trace_id})

