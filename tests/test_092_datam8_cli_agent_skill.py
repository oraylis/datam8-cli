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
        "agent-command-selection.md",
        "metadata-model-coverage.md",
        "zone-locator-resolution.md",
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
        "references/agent-command-selection.md",
        "references/metadata-model-coverage.md",
        "references/zone-locator-resolution.md",
    ]:
        assert reference in text
    assert "Never edit entity JSON files directly" in text
    assert "Never use `datam8 sources import`" in text
    assert "datam8 entities import external" in text
    assert "datam8 entities import internal" in text
    assert "First-use bootstrap" in text
    assert "datam8 --help" in text
    assert "localFolderName" in text
    assert "Do not invent commands from common CLI patterns" in text


def test_first_use_bootstrap_is_documented() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    workflows = (SKILL_DIR / "references/workflows.md").read_text(encoding="utf-8")
    contract = (SKILL_DIR / "references/cli-contract.md").read_text(encoding="utf-8")

    for text in [skill, workflows, contract]:
        assert "datam8 --help" in text
        assert ".dm8s" in text
        assert "CLI" in text or "cli" in text
    assert "do not ask onboarding questions" in workflows
    assert "do not ask generic onboarding questions" in contract


def test_command_discovery_rules_are_documented() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    workflows = (SKILL_DIR / "references/workflows.md").read_text(encoding="utf-8")
    selection = (SKILL_DIR / "references/agent-command-selection.md").read_text(encoding="utf-8")
    contract = (SKILL_DIR / "references/cli-contract.md").read_text(encoding="utf-8")

    for text in [skill, workflows, selection, contract]:
        assert "datam8 sources --help" in text
    for text in [skill, workflows, selection]:
        assert "Do not invent commands from common CLI patterns" in text
    assert "Command discovery" in contract
    assert "use only listed subcommands and options" in contract


def test_zone_locator_resolution_is_documented() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    workflows = (SKILL_DIR / "references/workflows.md").read_text(encoding="utf-8")
    selection = (SKILL_DIR / "references/agent-command-selection.md").read_text(encoding="utf-8")
    zone_reference = (SKILL_DIR / "references/zone-locator-resolution.md").read_text(
        encoding="utf-8"
    )

    for text in [skill, workflows, selection, zone_reference]:
        assert "localFolderName" in text
        assert "zones/<" in text or "zones/" in text
        assert "modelEntities/<" in text
        assert "datam8 show zones/<zone-name> --json" in text
    assert "Never use the natural zone word directly as a model folder" in zone_reference
    assert "Ask for the target folder below the zone root" in zone_reference
    assert "Mandatory zone preflight" in skill
    assert "Mandatory preflight before mutations" in zone_reference
    assert "blocking preflight" in workflows
    assert "trailing slash" in skill
    assert "modelEntities/010-Stage/" in zone_reference
    assert "Folder locators" in (SKILL_DIR / "references/cli-contract.md").read_text(
        encoding="utf-8"
    )
    assert "Do not run `entities import external` or `entities import external-all`" in (
        SKILL_DIR / "references/cli-contract.md"
    ).read_text(encoding="utf-8")
    assert "Never import to `modelEntities/stage`" in selection
    assert "Never run `datam8 entities import external modelEntities/stage/...`" in zone_reference
    assert "final parent folder" in skill
    assert "must not add a source-schema folder" in (SKILL_DIR / "references/cli-contract.md").read_text(
        encoding="utf-8"
    )


def test_openai_agent_metadata() -> None:
    data = yaml.safe_load((SKILL_DIR / "agents/openai.yaml").read_text(encoding="utf-8"))
    assert data["interface"]["display_name"] == "Datam8 CLI Agent"
    assert data["interface"]["short_description"]
