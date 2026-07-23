from pathlib import Path

from datam8 import solution
from datam8_model import base
from datam8_model.solution import Solution


def test_init_solution_creates_loadable_defaults(tmp_path: Path) -> None:
    solution_path = tmp_path / "blank" / "Blank.dm8s"

    solution.init_solution(solution_path)

    loaded = Solution.from_json_file(solution_path)
    assert loaded.modelPath == Path("model")
    assert loaded.basePath == Path("base")
    expected_files = {
        "AttributeTypes.json",
        "DataTypes.json",
        "Properties.json",
        "PropertyValues.json",
        "Zones.json",
        "DataSources.json",
        "DataSourceTypes.json",
        "DataProducts.json",
    }
    assert expected_files <= {path.name for path in (solution_path.parent / "base").glob("*.json")}
    for filename in expected_files:
        base.BaseEntities.from_json_file(solution_path.parent / "base" / filename)
