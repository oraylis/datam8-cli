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

import pathlib
import sys

import rich
import typer

from dm8gen import config, migration_v1, opts, parser_v1, utils

app = typer.Typer()

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


@app.command("migrate")
def command(
    solution_path: opts.SolutionPath,
    output_dir: opts.MigrationOutputDir = pathlib.Path("migration"),
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
):
    """Migrate solution model."""
    config.log_level = log_level
    config.lazy = False
    config.solution_path = solution_path
    config.solution_folder_path = solution_path.parent.absolute()

    solution = parser_v1.parse_solution_file(solution_path)

    utils.delete_path(output_dir, recursive=True)
    utils.mkdir(output_dir / "Model", recursive=True)

    migration_v1.migrate_base_entities(
        base_dir_path=config.solution_folder_path / solution.basePath,
        output_path=output_dir / "Base",
    )

    migration_v1.migrate_zones(solution, output_dir / "Base" / "zones.json")
    migration_v1.create_new_databricks_solution(output_dir / solution_path.name)

    # TODO: add more entries for raw/stage, which need to be merged some way
    tags: list[str] = []
    tags.extend(
        migration_v1.migrate_model_entities(
            model_dir_path=config.solution_folder_path / solution.corePath,
            output_path=output_dir / "Model" / solution.AreaTypes_1.Core,
        )
    )
    tags.extend(
        migration_v1.migrate_model_entities(
            model_dir_path=config.solution_folder_path / solution.curatedPath,
            output_path=output_dir / "Model" / solution.AreaTypes_1.Curated,
        ),
    )

    migration_v1.create_new_properties(list(set(tags)), output_dir / "Base")

    rich.print(f"Migration successfully written to {output_dir.as_posix()}")
