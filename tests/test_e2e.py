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
