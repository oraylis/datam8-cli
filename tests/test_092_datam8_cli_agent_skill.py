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

from pathlib import Path

import yaml

SKILL_DIR = Path("skills/datam8-cli-agent")


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, raw, _ = text.split("---", 2)
    return yaml.safe_load(raw)


def test_skill_structure() -> None:
    assert (SKILL_DIR / "SKILL.md").exists()
    assert (SKILL_DIR / "agents/openai.yaml").exists()
    for reference in [
        "cli-contract.md",
        "workflows.md",
        "safety-rules.md",
        "natural-language-examples.md",
    ]:
        assert (SKILL_DIR / "references" / reference).exists()


def test_skill_frontmatter_is_standard() -> None:
    frontmatter = _frontmatter(SKILL_DIR / "SKILL.md")
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "datam8-cli-agent"
    assert frontmatter["name"].islower()
    assert frontmatter["description"]
    assert frontmatter["description"] == frontmatter["description"].lower()
    assert "use this skill when" in frontmatter["description"]


def test_skill_rules_and_references_are_present() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for reference in [
        "references/cli-contract.md",
        "references/workflows.md",
        "references/safety-rules.md",
        "references/natural-language-examples.md",
    ]:
        assert reference in text
    assert "Never edit entity JSON files directly" in text
    assert "Never use `datam8 sources import`" in text
    assert "datam8 entities import external" in text
    assert "datam8 entities import internal" in text


def test_openai_agent_metadata() -> None:
    data = yaml.safe_load((SKILL_DIR / "agents/openai.yaml").read_text(encoding="utf-8"))
    assert data["interface"]["display_name"] == "Datam8 CLI Agent"
    assert data["interface"]["short_description"]
