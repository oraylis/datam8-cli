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

from .cmd import entities, functions, migrate, plugin, root, secret, solution, sources

app = root.app
app.registered_commands.extend(entities.app.registered_commands)
app.add_typer(solution.app)
app.add_typer(sources.app)
app.add_typer(plugin.app)
app.add_typer(secret.app)
app.add_typer(migrate.app)
app.add_typer(functions.app)


if __name__ == "__main__":
    app()
