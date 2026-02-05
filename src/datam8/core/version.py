from __future__ import annotations

import importlib.metadata


def get_version() -> str:
    try:
        return importlib.metadata.version("datam8")
    except Exception:
        return "0.0.0"

