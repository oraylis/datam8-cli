# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from pathlib import Path

import pytest

from datam8 import function_sources


class FunctionModelStub:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get_base_path_for_entity_type(self, _entity_type) -> Path:
        return self.root

    def get_entity_by_locator(self, _locator):
        return object()


def test_function_source_lifecycle_is_atomic_and_prunes_directories(
    tmp_path: Path,
) -> None:
    datam8_model = FunctionModelStub(tmp_path / "Model")
    locator = "modelEntities/curated/Customer"

    function_sources.write_source(
        datam8_model,  # type: ignore[arg-type]
        locator,
        "helpers/normalize.sql",
        "select 1",
    )
    assert (
        function_sources.read_source(
            datam8_model,  # type: ignore[arg-type]
            locator,
            "helpers/normalize.sql",
        )
        == "select 1"
    )

    function_sources.rename_source(
        datam8_model,  # type: ignore[arg-type]
        locator,
        "helpers/normalize.sql",
        "transform.sql",
    )
    function_sources.delete_source(
        datam8_model,  # type: ignore[arg-type]
        locator,
        "transform.sql",
    )

    entity_root = tmp_path / "Model" / "curated" / "Customer"
    assert not (entity_root / "helpers").exists()
    assert entity_root.exists()
    assert not list(entity_root.glob("*.tmp"))


@pytest.mark.parametrize(
    "source",
    [
        "",
        "../secret.sql",
        "functions/../../secret.sql",
        "/absolute.sql",
        r"C:\absolute.sql",
        r"\\server\share\source.sql",
        "functions//source.sql",
        "./source.sql",
    ],
)
def test_function_source_rejects_unsafe_paths(tmp_path: Path, source: str) -> None:
    datam8_model = FunctionModelStub(tmp_path / "Model")
    with pytest.raises(ValueError):
        function_sources.source_path(
            datam8_model,  # type: ignore[arg-type]
            "modelEntities/curated/Customer",
            source,
        )


def test_function_source_rejects_symlink_escape(tmp_path: Path) -> None:
    model_root = tmp_path / "Model"
    entity_root = model_root / "curated" / "Customer"
    outside = tmp_path / "outside"
    entity_root.mkdir(parents=True)
    outside.mkdir()

    link = entity_root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is not permitted in this environment")

    datam8_model = FunctionModelStub(model_root)
    with pytest.raises(ValueError, match="outside"):
        function_sources.source_path(
            datam8_model,  # type: ignore[arg-type]
            "modelEntities/curated/Customer",
            "linked/source.sql",
        )


def test_function_directory_move_can_be_rolled_back(tmp_path: Path) -> None:
    model_root = tmp_path / "Model"
    source_root = model_root / "curated" / "Customer"
    source_root.mkdir(parents=True)
    (source_root / "function.sql").write_text("select 1", encoding="utf-8")
    datam8_model = FunctionModelStub(model_root)

    move = function_sources.move_entity_directory(
        datam8_model,  # type: ignore[arg-type]
        "modelEntities/curated/Customer",
        "modelEntities/core/Customer",
    )

    assert move is not None
    assert not source_root.exists()
    assert (model_root / "core" / "Customer" / "function.sql").exists()

    move.rollback()
    assert (source_root / "function.sql").exists()
    assert not (model_root / "core" / "Customer").exists()
