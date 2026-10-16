"""Normalize legacy solution JSON before the strict UTF-8 model readers run."""

import json
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from datam8 import logging
from datam8.errors import Datam8ValidationError
from datam8_model.solution import Solution

logger = logging.getLogger(__name__)


def ensure_utf8_solution(solution_path: Path) -> None:
    pending: dict[Path, tuple[bytes, bytes]] = {}

    def read(path: Path) -> str:
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1252")
                json.loads(text)
            except ValueError as err:
                raise Datam8ValidationError(
                    message=f"Cannot decode solution JSON as UTF-8 or Windows-1252: {path}",
                    details={"path": str(path)},
                ) from err
            if path.is_symlink():
                raise Datam8ValidationError(message=f"Cannot convert a linked JSON file: {path}")
            pending[path] = (raw, text.encode("utf-8"))
            return text

    solution = Solution.model_validate_json(read(solution_path))
    for directory in (solution.basePath, solution.modelPath):
        for path in sorted((solution_path.parent / directory).rglob("*.json")):
            read(path)

    for path, (original, encoded) in pending.items():
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
            shutil.copymode(path, temporary)
            if path.read_bytes() != original:
                raise OSError("File changed during UTF-8 conversion")
            temporary.replace(path)
        except OSError as err:
            raise Datam8ValidationError(
                message=f"Cannot convert solution JSON to UTF-8: {path}: {err}",
                details={"path": str(path)},
            ) from err
        finally:
            if temporary is not None and temporary.exists():
                temporary.chmod(0o600)
                temporary.unlink()
        logger.warning("Converted Windows-1252 JSON to UTF-8: %s", path)
