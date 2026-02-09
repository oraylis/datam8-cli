from __future__ import annotations

import asyncio
from pathlib import Path

import datam8.utils as utils_mod
from datam8 import config, opts, parser
from datam8.core.validation import validate_solution_dm8s


def test_print_progress_async_handles_unicode_error_and_awaits(monkeypatch) -> None:
    called = False

    class ExplodingProgress:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def __enter__(self):
            raise UnicodeEncodeError(
                "charmap",
                "\u280b",
                0,
                1,
                "character maps to <undefined>",
            )

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type, exc, tb
            return False

    async def _sample_async() -> int:
        nonlocal called
        await asyncio.sleep(0)
        called = True
        return 42

    monkeypatch.setattr(utils_mod, "Progress", ExplodingProgress)
    wrapped = utils_mod.print_progress_async("Parsing files...")(_sample_async)

    previous_log_level = config.log_level
    config.log_level = opts.LogLevels.WARNING
    try:
        result = asyncio.run(wrapped())
    finally:
        config.log_level = previous_log_level

    assert result == 42
    assert called is True


def test_validate_solution_maps_unicode_errors_to_unknown(monkeypatch, tmp_path: Path) -> None:
    fixture_dm8s = Path(__file__).parent / "fixtures" / "job_solution" / "TestSolution.dm8s"
    dm8s_path = tmp_path / "TestSolution.dm8s"
    dm8s_path.write_text(fixture_dm8s.read_text(encoding="utf-8"), encoding="utf-8")

    async def _raise_unicode_error(*args, **kwargs):
        _ = args, kwargs
        raise UnicodeEncodeError(
            "charmap",
            "\u280b",
            0,
            1,
            "character maps to <undefined>",
        )

    monkeypatch.setattr(parser, "parse_full_solution_async", _raise_unicode_error)

    report = asyncio.run(validate_solution_dm8s(dm8s_path))

    assert report["ok"] is False
    assert len(report["errors"]) == 1
    assert report["errors"][0]["code"] == "UNKNOWN_ERROR"
    assert "Console encoding error" in report["errors"][0]["message"]
