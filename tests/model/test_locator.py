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

import pytest
import pytest_cases

from datam8.model.locator import ROOT_LOCATOR, Locator


def _build_locator(p: str | None, name: str | None) -> Locator:
    locator = Locator("modelEntities", p.split("/") if p else [], name)
    return locator


def test_root_locator():
    assert "/" == str(ROOT_LOCATOR)
    assert "/" == ROOT_LOCATOR
    assert ROOT_LOCATOR == "/"


@pytest_cases.parametrize(
    ["left", "right", "expect"],
    [
        (_build_locator("A/A/A", None), _build_locator("A/A/A", None), True),
        (_build_locator("A/A/A", "A"), _build_locator("A/A/A", "A"), True),
        (_build_locator("A", "A"), _build_locator("A/A", "A"), False),
        (_build_locator("A/A/A/D", "C"), _build_locator("A/A/A", None), True),
        (_build_locator("A/A", None), ROOT_LOCATOR, True),
        (_build_locator("A", "A"), ROOT_LOCATOR, True),
        (_build_locator("A", "B"), _build_locator("A", None), True),
        (_build_locator("A", "A"), _build_locator("A/B", None), False),
        (_build_locator("A", "A"), _build_locator("A/B", None), False),
    ],
)
def test_contains(left: Locator | None, right: Locator, expect: bool):
    assert (left in right) == expect, (
        f"Locator 'IN' comparison failed: '{left}' in '{right}' - expected {expect}"
    )


def test_contains_raises_on_none():
    with pytest.raises(TypeError):
        assert None in ROOT_LOCATOR


@pytest_cases.parametrize(
    ["left", "right", "expect"],
    [
        (_build_locator("A/A", "A"), _build_locator("A/B", None), _build_locator("A/B/A", "A")),
        (_build_locator("A/A", "A"), _build_locator("A/B/C", None), _build_locator("A/B/C/A", "A")),
        (_build_locator("A/A/C", "A"), _build_locator("A/B", None), _build_locator("A/B/A/C", "A")),
        (_build_locator("A", "A"), _build_locator("B/A", "A"), _build_locator("B/A/A", "A")),
        (_build_locator("A", "A"), ROOT_LOCATOR, _build_locator("A", "A")),
        (_build_locator(None, "A"), _build_locator("A", "B"), _build_locator("A", "A")),
        (
            _build_locator("A/B/C/D", "E"),
            _build_locator("D/C/B/A", None),
            _build_locator("D/C/B/A/A/B/C/D", "E"),
        ),
        (Locator.from_path("folders/test"), Locator.from_path("modelEntities/test/A"), None),
        (
            Locator.from_path("properties/jobs-new"),
            Locator.from_path("properties/jobs"),
            Locator.from_path("properties/jobs-new"),
        ),
    ],
)
def test_rebase(left: Locator, right: Locator, expect: Locator | None):
    rebased = left.rebase(right)
    if expect is None:
        assert rebased is None, f"Rebased locator not as expected: {rebased} vs {expect}"
    else:
        assert rebased == expect, f"Rebased locator not as expected: {rebased} vs {expect}"


def test_parents():
    folders = ["A", "A", "A"]
    parents = Locator("modelEntities", folders[:], "A").parents

    first_parent = next(parents)
    assert first_parent == Locator("folders", folders[:-1], "A")

    second_parent = next(parents)
    assert second_parent == Locator("folders", folders[:-2], "A")

    third_parent = next(parents)
    assert third_parent == Locator("folders", folders[:-3], "A")

    fourth_parent = next(parents)
    assert fourth_parent == Locator("folders", folders[:-3], None)

    fifth_parent = next(parents, None)
    assert fifth_parent is None, "There should be no more parents"
