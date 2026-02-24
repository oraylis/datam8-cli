# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DataM8 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from datam8.core.errors import Datam8ValidationError
from datam8.core.lock import SolutionLock
from datam8.core.parse_utils import parse_duration_seconds
from datam8.core.runtime_meta import get_version


@dataclass(frozen=True)
class GlobalOptions:
    """Global options shared by all CLI commands."""

    solution: str | None
    json_output: bool
    quiet: bool
    verbose: bool
    log_file: str | None
    log_level: str
    lock_timeout: str
    no_lock: bool


def version_callback(value: bool) -> None:
    """Print CLI version when --version is passed."""
    if value:
        typer.echo(get_version())
        raise typer.Exit(code=0)


def build_global_options(
    *,
    solution: str | None,
    json_output: bool,
    quiet: bool,
    verbose: bool,
    log_file: str | None,
    log_level: str,
    lock_timeout: str,
    no_lock: bool,
) -> GlobalOptions:
    """Build a validated global options object."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together.")
    return GlobalOptions(
        solution=solution or os.environ.get("DATAM8_SOLUTION_PATH"),
        json_output=json_output,
        quiet=quiet,
        verbose=verbose,
        log_file=log_file,
        log_level=log_level,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )


def make_global_options(
    *,
    solution: Path | str | None = None,
    json_output: bool = False,
    quiet: bool = False,
    verbose: bool = False,
    log_file: str | None = None,
    log_level: str = "info",
    lock_timeout: str = "10s",
    no_lock: bool = False,
) -> GlobalOptions:
    """Create global options directly from command arguments."""
    normalized_solution: str | None
    if isinstance(solution, Path):
        normalized_solution = str(solution)
    else:
        normalized_solution = solution
    return build_global_options(
        solution=normalized_solution,
        json_output=json_output,
        quiet=quiet,
        verbose=verbose,
        log_file=log_file,
        log_level=log_level,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )


def resolve_solution_path(opts: GlobalOptions, solution_path: str | None = None) -> str | None:
    """Resolve explicit solution_path over global --solution."""
    return solution_path or opts.solution


def emit_human(message: str) -> None:
    """Write a single human-readable line to stdout."""
    sys.stdout.write((message or "") + "\n")
    sys.stdout.flush()


def emit_json(payload: Any) -> None:
    """Write a JSON payload to stdout."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_result(opts: GlobalOptions, payload: Any, *, human_lines: list[str] | None = None) -> None:
    """Emit command result in JSON or human format."""
    if opts.json_output:
        emit_json(payload)
        return
    if human_lines:
        for line in human_lines:
            if line or not opts.quiet:
                emit_human(line)
        return
    emit_human(json.dumps(payload, indent=2, ensure_ascii=False))


def read_json_arg(arg: str) -> Any:
    """Read JSON from inline string, @file, or stdin via '-'."""
    value = (arg or "").strip()
    if value == "-":
        value = sys.stdin.read()
    elif value.startswith("@"):
        value = Path(value[1:]).read_text(encoding="utf-8")
    return json.loads(value)


def read_text_arg(arg: str) -> str:
    """Read text from inline string, @file, or stdin via '-'."""
    value = arg or ""
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    return value


def open_in_editor(*, suffix: str, initial_text: str) -> str:
    """Open an editor and return updated file content."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        raise Datam8ValidationError(message="No editor configured.", details={"hint": "Set EDITOR or VISUAL."})

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=suffix, newline="\n") as tmp:
        tmp.write(initial_text)
        tmp_path = tmp.name
    try:
        subprocess.check_call([editor, tmp_path])
        return Path(tmp_path).read_text(encoding="utf-8")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def lock_context(*, opts: GlobalOptions, lock_file_root: Path):
    """Return a lock context manager unless --no-lock is set."""
    if opts.no_lock:
        return nullcontext()
    timeout_seconds = parse_duration_seconds(opts.lock_timeout)
    return SolutionLock(lock_file_root / ".datam8.lock", timeout_seconds=timeout_seconds)
