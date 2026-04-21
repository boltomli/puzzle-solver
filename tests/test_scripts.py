"""Tests for the scripts page logic — specifically the deduction creation from analysis facts."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.puzzle import (
    ConfidenceLevel,
    DeductionStatus,
)
from src.storage.json_store import JsonStore
from src.ui.state import AppState


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    temp_dir = tempfile.mkdtemp(prefix="puzzle_scripts_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def state(temp_data_dir):
    """Create an AppState with a temporary data directory."""
    store = JsonStore(data_dir=temp_data_dir)
    return AppState(store=store)


@pytest.fixture
def project_with_entities(state, monkeypatch):
    """Create a project with characters, locations, and time slots.

    Also patches the module-level app_state in scripts.py to use this state.
    """
    import src.ui.pages.scripts as scripts_mod

    state.create_project(name="Test Mystery", time_slots=["14:00", "15:00"])
    state.add_character(name="Alice")
    state.add_character(name="Bob")
    state.add_location(name="图书馆")
    state.add_location(name="花园")
    monkeypatch.setattr(scripts_mod, "app_state", state)
    return state.current_project


class TestCreateDeductionsFromFacts:
    """Tests for _create_deductions_from_facts logic."""

    def test_creates_pending_deductions(self, state, project_with_entities):
        """Direct facts should become pending Deductions, not Facts."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        alice = proj.characters[0]
        lib = proj.locations[0]

        direct_facts = [
            {
                "character_name": "Alice",
                "location_name": "图书馆",
                "time_slot": "14:00",
                "confidence": "high",
                "evidence": "剧本明确说明 Alice 在 14:00 在图书馆",
            }
        ]

        created = _create_deductions_from_facts(proj, direct_facts, "script-1")
        assert created == 1
        assert len(proj.deductions) == 1
        ded = proj.deductions[0]
        assert ded.status == DeductionStatus.pending
        assert ded.character_id == alice.id
        assert ded.location_id == lib.id
        ts_map = {ts.label: ts for ts in proj.time_slots}
        assert ded.time_slot == ts_map["14:00"].id
        assert ded.confidence == ConfidenceLevel.high
        assert "script-1" in ded.supporting_script_ids

    def test_skips_unknown_character(self, state, project_with_entities):
        """Facts with unresolvable character_name should be skipped."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        direct_facts = [
            {
                "character_name": "UnknownPerson",
                "location_name": "图书馆",
                "time_slot": "14:00",
                "confidence": "medium",
            }
        ]

        created = _create_deductions_from_facts(proj, direct_facts, "script-1")
        assert created == 0
        assert len(proj.deductions) == 0

    def test_skips_unknown_location(self, state, project_with_entities):
        """Facts with unresolvable location_name should be skipped."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        direct_facts = [
            {
                "character_name": "Alice",
                "location_name": "未知地点",
                "time_slot": "14:00",
                "confidence": "medium",
            }
        ]

        created = _create_deductions_from_facts(proj, direct_facts, "script-1")
        assert created == 0

    def test_skips_invalid_time_slot(self, state, project_with_entities):
        """Facts with invalid time_slot format should be skipped."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        direct_facts = [
            {
                "character_name": "Alice",
                "location_name": "图书馆",
                "time_slot": "invalid",
                "confidence": "medium",
            }
        ]

        created = _create_deductions_from_facts(proj, direct_facts, "script-1")
        assert created == 0

    def test_multiple_facts(self, state, project_with_entities):
        """Multiple valid facts should all become deductions."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        direct_facts = [
            {
                "character_name": "Alice",
                "location_name": "图书馆",
                "time_slot": "14:00",
                "confidence": "high",
                "evidence": "证据1",
            },
            {
                "character_name": "Bob",
                "location_name": "花园",
                "time_slot": "15:00",
                "confidence": "medium",
                "evidence": "证据2",
            },
        ]

        created = _create_deductions_from_facts(proj, direct_facts, "script-1")
        assert created == 2
        assert len(proj.deductions) == 2
        assert all(d.status == DeductionStatus.pending for d in proj.deductions)

    def test_default_confidence(self, state, project_with_entities):
        """Unknown confidence strings should default to medium."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        direct_facts = [
            {
                "character_name": "Alice",
                "location_name": "图书馆",
                "time_slot": "14:00",
                "confidence": "unknown_level",
            }
        ]

        created = _create_deductions_from_facts(proj, direct_facts, "script-1")
        assert created == 1
        assert proj.deductions[0].confidence == ConfidenceLevel.medium

    def test_default_reasoning_when_no_evidence(self, state, project_with_entities):
        """When no evidence is provided, a default reasoning string is generated."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        direct_facts = [
            {
                "character_name": "Alice",
                "location_name": "图书馆",
                "time_slot": "14:00",
                "confidence": "medium",
                # no evidence key
            }
        ]

        created = _create_deductions_from_facts(proj, direct_facts, "script-1")
        assert created == 1
        assert "Alice" in proj.deductions[0].reasoning
        assert "图书馆" in proj.deductions[0].reasoning

    def test_empty_facts_list(self, state, project_with_entities):
        """Empty facts list should create zero deductions."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        created = _create_deductions_from_facts(proj, [], "script-1")
        assert created == 0

    def test_resolves_character_and_location_aliases(self, state, project_with_entities):
        """Merged aliases should resolve to existing canonical entities."""
        from src.ui.pages.scripts import _create_deductions_from_facts

        proj = project_with_entities
        alice = proj.characters[0]
        library = proj.locations[0]
        state.merge_character("艾丽斯", alice.id)
        state.merge_location("藏书室", library.id)

        created = _create_deductions_from_facts(
            proj,
            [
                {
                    "character_name": "艾丽斯",
                    "location_name": "藏书室",
                    "time_slot": "14:00",
                    "confidence": "high",
                }
            ],
            "script-1",
        )

        assert created == 1
        assert len(proj.deductions) == 1
        deduction = proj.deductions[0]
        assert deduction.character_id == alice.id
        assert deduction.location_id == library.id


class TestIsApiConfigured:
    """Tests for _is_api_configured helper."""

    def test_not_configured_by_default(self, tmp_path, monkeypatch):
        """With no config file, API should not be configured."""
        import src.services.config as config_mod
        from src.ui.pages.scripts import _is_api_configured

        monkeypatch.setattr(config_mod, "_CONFIG_PATH", tmp_path / "config.json")
        assert _is_api_configured() is False

    def test_configured_with_base_url_and_model(self, tmp_path, monkeypatch):
        """API is configured when base_url and model are set (key can be empty)."""
        import json

        import src.services.config as config_mod
        from src.ui.pages.scripts import _is_api_configured

        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)
        assert _is_api_configured() is True

    def test_not_configured_without_model(self, tmp_path, monkeypatch):
        """API is not configured when model is missing."""
        import json

        import src.services.config as config_mod
        from src.ui.pages.scripts import _is_api_configured

        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "key",
                    "model": "",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)
        assert _is_api_configured() is False


@pytest.mark.asyncio
async def test_run_script_analysis_surfaces_save_failure_without_showing_results(
    state, monkeypatch
):
    """Auto analysis should show explicit save-failure feedback and stop the success flow."""
    import src.ui.pages.scripts as scripts_mod

    monkeypatch.setattr(scripts_mod, "app_state", state)
    state.create_project(name="Test")
    script = state.add_script(raw_text="Some script text", title="Scene 1")

    analysis_result = {
        "characters_mentioned": [{"name": "Alice"}],
        "locations_mentioned": [],
        "time_references": [],
        "direct_facts": [],
    }

    class _StubDeductionService:
        async def analyze_script(self, proj, current_script, ts_by_id):
            assert proj is state.current_project
            assert current_script.id == script.id
            assert ts_by_id == state.cache.ts_by_id
            return analysis_result

    shown_messages: list[tuple[str, str | None]] = []
    refresh_calls: list[str] = []
    shown_dialogs: list[dict] = []

    import src.services.deduction as deduction_mod

    monkeypatch.setattr(deduction_mod, "DeductionService", _StubDeductionService)
    monkeypatch.setattr(
        state,
        "save_script_analysis",
        lambda script_id, result: False,
    )
    monkeypatch.setattr(
        scripts_mod,
        "_show_analysis_results_dialog",
        lambda *args, **kwargs: shown_dialogs.append({"args": args, "kwargs": kwargs}),
    )

    page = SimpleNamespace(update=lambda: None)

    await scripts_mod._run_script_analysis(
        page,
        script.id,
        lambda: refresh_calls.append("refresh"),
        lambda message, color=None: shown_messages.append((message, color)),
    )

    assert shown_messages == [
        ("🤖 正在分析剧本...", scripts_mod.ft.Colors.BLUE),
        ("剧本分析已完成，但保存失败，请重试", scripts_mod.ft.Colors.RED),
    ]
    assert refresh_calls == []
    assert shown_dialogs == []
    assert script.analysis_result is None
