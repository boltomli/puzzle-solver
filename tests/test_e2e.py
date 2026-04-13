"""End-to-end tests for the puzzle solver application."""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.models.puzzle import (
    Character,
    CharacterStatus,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    Fact,
    HintType,
    Location,
    Project,
    Rejection,
    SourceType,
)
from src.storage.json_store import JsonStore
from src.ui.state import AppState


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    temp_dir = tempfile.mkdtemp(prefix="puzzle_e2e_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def state(temp_data_dir):
    """Create an AppState with a temporary data directory."""
    store = JsonStore(data_dir=temp_data_dir)
    return AppState(store=store)


@pytest.fixture
def mock_analysis_result():
    return {
        "characters_mentioned": [
            {"character_id": None, "name": "Emma", "is_new": True, "context": "坐在草坪上"}
        ],
        "locations_mentioned": [
            {"location_id": None, "name": "草坪", "is_new": True, "context": "Emma坐在此处"}
        ],
        "time_references": [
            {"time_slot": "15:00", "reference_text": "15:00", "is_explicit": True}
        ],
        "direct_facts": [
            {
                "character_name": "Emma",
                "location_name": "草坪",
                "time_slot": "15:00",
                "confidence": "certain",
                "evidence": "15:00，Emma 坐在草坪上",
            }
        ],
        "alias_candidates": [],
    }


class TestE2EFixtures:
    def test_state_fixture_works(self, state):
        assert state.current_project is None
        assert state.store is not None

    def test_mock_analysis_result_structure(self, mock_analysis_result):
        assert "characters_mentioned" in mock_analysis_result
        assert mock_analysis_result["characters_mentioned"][0]["name"] == "Emma"
        assert mock_analysis_result["direct_facts"][0]["time_slot"] == "15:00"


class TestCoreE2EFlow:
    def test_full_script_to_matrix_flow(self, state, mock_analysis_result):
        """Test: create_project → add_script → extract entities from analysis → add entities → add fact → verify matrix."""
        # Step 1: Create project
        project = state.create_project(name="E2E测试项目")
        assert state.current_project is not None
        assert state.current_project.name == "E2E测试项目"

        # Step 2: Add script
        script = state.add_script(
            raw_text="15:00，Emma 坐在草坪上",
            title="测试剧本"
        )
        assert len(state.current_project.scripts) == 1
        assert script.raw_text == "15:00，Emma 坐在草坪上"

        # Step 3: Simulate saving analysis result (as if AI analyzed it)
        saved = state.save_script_analysis(script.id, mock_analysis_result)
        assert saved is True
        assert script.analysis_result is not None

        # Step 4: Extract entities from analysis result and add them
        # (Simulating what the UI does when user clicks "Add All")
        for ch in mock_analysis_result["characters_mentioned"]:
            if ch.get("is_new"):
                state.add_character(name=ch["name"])
        for lo in mock_analysis_result["locations_mentioned"]:
            if lo.get("is_new"):
                state.add_location(name=lo["name"])
        for tr in mock_analysis_result["time_references"]:
            ts = tr.get("time_slot", "")
            if ts:
                state.add_time_slot(ts)

        assert len(state.current_project.characters) == 1
        assert state.current_project.characters[0].name == "Emma"
        assert len(state.current_project.locations) == 1
        assert state.current_project.locations[0].name == "草坪"
        assert "15:00" in state.current_project.time_slots

        # Step 5: Add fact from analysis direct_facts
        emma = state.current_project.characters[0]
        lawn = state.current_project.locations[0]
        fact = state.add_fact(
            character_id=emma.id,
            location_id=lawn.id,
            time_slot="15:00",
            source_type=SourceType.script_explicit,
            source_evidence="15:00，Emma 坐在草坪上",
        )
        assert len(state.current_project.facts) == 1

        # Step 6: Verify matrix data
        from src.ui.pages.matrix import build_matrix_data
        rows = build_matrix_data(state.current_project)
        assert len(rows) == 1
        emma_row = rows[0]
        assert emma_row["character"] == "Emma"
        assert emma_row["15:00"] == "草坪"
        assert emma_row["15:00_status"] == "confirmed"

    def test_script_analysis_to_deduction_flow(self, state, mock_analysis_result):
        """Test creating deductions from analysis using _create_single_deduction."""
        import src.ui.pages.scripts as scripts_mod

        state.create_project(name="推断测试")
        state.add_character(name="Emma")
        state.add_location(name="草坪")
        state.add_time_slot("15:00")
        script = state.add_script(raw_text="15:00，Emma 坐在草坪上")

        # Patch scripts module's app_state
        original_app_state = scripts_mod.app_state
        scripts_mod.app_state = state
        try:
            proj = state.current_project
            fact_dict = mock_analysis_result["direct_facts"][0]
            success = scripts_mod._create_single_deduction(proj, fact_dict, script.id)
            assert success is True
            assert len(proj.deductions) == 1
            ded = proj.deductions[0]
            assert ded.status == DeductionStatus.pending
            assert ded.confidence == ConfidenceLevel.certain
        finally:
            scripts_mod.app_state = original_app_state

    def test_multiple_scripts_accumulate(self, state):
        """Multiple scripts should have correct source_order."""
        state.create_project(name="多剧本测试")
        s1 = state.add_script(raw_text="第一幕")
        s2 = state.add_script(raw_text="第二幕")
        s3 = state.add_script(raw_text="第三幕")
        assert s1.metadata.source_order == 1
        assert s2.metadata.source_order == 2
        assert s3.metadata.source_order == 3
        assert len(state.current_project.scripts) == 3

    def test_persistence_across_reload(self, state):
        """Data should survive save → load cycle."""
        project = state.create_project(name="持久化测试", time_slots=["10:00"])
        state.add_character(name="TestChar")
        state.add_location(name="TestLoc")
        pid = project.id

        # Reload from disk
        state.current_project = None
        state.load_project(pid)
        assert state.current_project.name == "持久化测试"
        assert len(state.current_project.characters) == 1
        assert state.current_project.characters[0].name == "TestChar"
