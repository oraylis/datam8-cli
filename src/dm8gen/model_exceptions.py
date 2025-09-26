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

class EntityNotFoundError(Exception):
    def __init__(
        self,
        entity: str,
        msg: str = "Entity was not found in model: {}",
        inner_exceptions: list[Exception] | None = None,
    ):
        Exception.__init__(self, msg.format(entity))

        self.inner_exceptions = inner_exceptions
        self.message = msg.format(entity)


class InvalidLocatorError(Exception):
    def __init__(self, locator: str):
        super().__init__(f"Not a valid locator: {locator}")


class PropertiesNotResolvedError(Exception):
    def __init__(self, locator):
        super().__init__(
            f"Tried to access properties of unresolved entity '{locator}' yet"
        )


class InvalidGeneratorTargetError(Exception):
    def __init__(self, target_name: str):
        super().__init__(f"Generator target '{target_name}' is not defined")
