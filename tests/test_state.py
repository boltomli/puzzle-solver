"""Tests for the AppState manager."""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.models.puzzle import (
    CharacterStatus,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    HintType,
    SourceType,
)
from src.storage.json_store import JsonStore
from src.ui.state import AppState


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    temp_dir = tempfile.mkdtemp(prefix="puzzle_state_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def state(temp_data_dir):
    """Create an AppState with a temporary data directory."""
    store = JsonStore(data_dir=temp_data_dir)
    return AppState(store=store)


class TestAppStateProject:
    def test_create_project(self, state):
        state.create_project(name="Test Mystery", description="A test")
        assert state.current_project is not None
        assert state.current_project.name == "Test Mystery"
        assert state.current_project.description == "A test"

    def test_create_project_with_time_slots(self, state):
        state.create_project(name="Test", time_slots=["14:00", "15:00", "16:00"])
        assert len(state.current_project.time_slots) == 3

    def test_load_project(self, state):
        project = state.create_project(name="To Load")
        project_id = project.id
        # Clear current
        state.current_project = None
        # Load
        state.load_project(project_id)
        assert state.current_project is not None
        assert state.current_project.id == project_id
        assert state.current_project.name == "To Load"

    def test_delete_project(self, state):
        project = state.create_project(name="To Delete")
        pid = project.id
        state.delete_project(pid)
        assert state.current_project is None
        # Should be gone from disk
        with pytest.raises(FileNotFoundError):
            state.store.load_project(pid)

    def test_delete_other_project(self, state):
        p1 = state.create_project(name="Keep")
        p2 = state.store.create_project(name="Delete Me")
        state.delete_project(p2.id)
        # Current project should still be p1
        assert state.current_project is not None
        assert state.current_project.id == p1.id

    def test_list_projects(self, state):
        state.create_project(name="A")
        state.store.create_project(name="B")
        summaries = state.list_projects()
        assert len(summaries) == 2

    def test_save_persists(self, state):
        project = state.create_project(name="Persist Test")
        project.name = "Updated Name"
        state.save()
        loaded = state.store.load_project(project.id)
        assert loaded.name == "Updated Name"


class TestAppStateCharacters:
    def test_add_character(self, state):
        state.create_project(name="Test")
        char = state.add_character(name="Alice", aliases=["A"])
        assert char.name == "Alice"
        assert len(state.current_project.characters) == 1
        # Verify persisted
        loaded = state.store.load_project(state.current_project.id)
        assert len(loaded.characters) == 1

    def test_add_character_no_project(self, state):
        with pytest.raises(ValueError, match="No project loaded"):
            state.add_character(name="Nobody")

    def test_update_character(self, state):
        state.create_project(name="Test")
        char = state.add_character(name="Alice")
        updated = state.update_character(
            char.id, name="Alice Updated", status=CharacterStatus.suspected
        )
        assert updated.name == "Alice Updated"
        assert updated.status == CharacterStatus.suspected

    def test_update_nonexistent_character(self, state):
        state.create_project(name="Test")
        result = state.update_character("nonexistent", name="X")
        assert result is None

    def test_remove_character(self, state):
        state.create_project(name="Test")
        char = state.add_character(name="Alice")
        removed = state.remove_character(char.id)
        assert removed is True
        assert len(state.current_project.characters) == 0

    def test_remove_nonexistent_character(self, state):
        state.create_project(name="Test")
        removed = state.remove_character("nonexistent")
        assert removed is False


class TestAppStateLocations:
    def test_add_location(self, state):
        state.create_project(name="Test")
        loc = state.add_location(name="Library", aliases=["图书馆"])
        assert loc.name == "Library"
        assert len(state.current_project.locations) == 1

    def test_update_location(self, state):
        state.create_project(name="Test")
        loc = state.add_location(name="Library")
        updated = state.update_location(loc.id, name="Big Library")
        assert updated.name == "Big Library"

    def test_remove_location(self, state):
        state.create_project(name="Test")
        loc = state.add_location(name="Library")
        removed = state.remove_location(loc.id)
        assert removed is True
        assert len(state.current_project.locations) == 0


class TestAppStateScripts:
    def test_add_script(self, state):
        state.create_project(name="Test")
        script = state.add_script(
            raw_text="Alice entered the library.",
            title="Scene 1",
            user_notes="Important scene",
        )
        assert script.title == "Scene 1"
        assert script.raw_text == "Alice entered the library."
        assert script.metadata.user_notes == "Important scene"
        assert script.metadata.source_order == 1

    def test_add_multiple_scripts_source_order(self, state):
        state.create_project(name="Test")
        s1 = state.add_script(raw_text="First")
        s2 = state.add_script(raw_text="Second")
        assert s1.metadata.source_order == 1
        assert s2.metadata.source_order == 2

    def test_update_script(self, state):
        state.create_project(name="Test")
        script = state.add_script(raw_text="Original text")
        updated = state.update_script(script.id, title="New Title")
        assert updated.title == "New Title"

    def test_remove_script(self, state):
        state.create_project(name="Test")
        script = state.add_script(raw_text="To delete")
        removed = state.remove_script(script.id)
        assert removed is True
        assert len(state.current_project.scripts) == 0


class TestAppStateFacts:
    def test_add_fact(self, state):
        state.create_project(name="Test", time_slots=["14:00"])
        char = state.add_character(name="Alice")
        loc = state.add_location(name="Library")
        fact = state.add_fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot="14:00",
            source_evidence="Manually observed",
        )
        assert fact.source_type == SourceType.user_input
        assert fact.source_evidence == "Manually observed"
        assert len(state.current_project.facts) == 1

    def test_remove_fact(self, state):
        state.create_project(name="Test", time_slots=["14:00"])
        char = state.add_character(name="Alice")
        loc = state.add_location(name="Library")
        fact = state.add_fact(character_id=char.id, location_id=loc.id, time_slot="14:00")
        removed = state.remove_fact(fact.id)
        assert removed is True
        assert len(state.current_project.facts) == 0

    def test_add_fact_no_project(self, state):
        with pytest.raises(ValueError, match="No project loaded"):
            state.add_fact(character_id="c1", location_id="l1", time_slot="14:00")


class TestAppStateTimeSlots:
    def test_add_time_slot(self, state):
        state.create_project(name="Test")
        added = state.add_time_slot("14:00")
        assert added is not None
        assert added.label == "14:00"
        assert len(state.current_project.time_slots) == 1
        assert state.current_project.time_slots[0].label == "14:00"

    def test_add_duplicate_time_slot(self, state):
        state.create_project(name="Test", time_slots=["14:00"])
        added = state.add_time_slot("14:00")
        assert added is None

    def test_add_invalid_time_slot(self, state):
        state.create_project(name="Test")
        with pytest.raises(ValueError, match="HH:MM"):
            state.add_time_slot("invalid")

    def test_remove_time_slot(self, state):
        state.create_project(name="Test", time_slots=["14:00", "15:00"])
        ts_to_remove = next(ts for ts in state.current_project.time_slots if ts.label == "14:00")
        removed = state.remove_time_slot(ts_to_remove.id)
        assert removed is True
        labels = [ts.label for ts in state.current_project.time_slots]
        assert "14:00" not in labels
        assert "15:00" in labels

    def test_time_slots_sorted(self, state):
        state.create_project(name="Test")
        state.add_time_slot("16:00")
        state.add_time_slot("14:00")
        state.add_time_slot("15:00")
        labels = [ts.label for ts in state.current_project.time_slots]
        assert labels == ["16:00", "14:00", "15:00"]


class TestAppStateHints:
    def test_add_hint(self, state):
        state.create_project(name="Test")
        hint = state.add_hint(
            hint_type=HintType.rule,
            content="One person per location",
        )
        assert hint.type == HintType.rule
        assert hint.content == "One person per location"
        assert len(state.current_project.hints) == 1

    def test_remove_hint(self, state):
        state.create_project(name="Test")
        hint = state.add_hint(hint_type=HintType.hint, content="A hint")
        removed = state.remove_hint(hint.id)
        assert removed is True
        assert len(state.current_project.hints) == 0

    def test_remove_nonexistent_hint(self, state):
        state.create_project(name="Test")
        removed = state.remove_hint("nonexistent")
        assert removed is False


class TestDeductionIndex:
    """Tests for the index-based deduplication system in AppState."""

    def _setup_project(self, state):
        """Helper to create a project with a character and location."""
        state.create_project(name="Test", time_slots=["14:00", "15:00"])
        char = state.add_character(name="Alice")
        loc = state.add_location(name="Library")
        return char, loc

    def _get_ts_id(self, state, label):
        """Helper to get time slot ID by label."""
        ts = next(ts for ts in state.current_project.time_slots if ts.label == label)
        return ts.id

    def _make_deduction(self, char, loc, time_slot):
        """Helper to create a Deduction object."""
        from src.models.puzzle import ConfidenceLevel, Deduction, DeductionStatus

        return Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=time_slot,
            confidence=ConfidenceLevel.medium,
            reasoning="Test reasoning",
            status=DeductionStatus.pending,
        )

    def test_add_deduction_rejects_existing_fact(self, state):
        """add_deduction returns False when triple already exists as a confirmed Fact."""
        char, loc = self._setup_project(state)
        ts_id = self._get_ts_id(state, "14:00")
        # Add a fact for the triple
        state.add_fact(character_id=char.id, location_id=loc.id, time_slot=ts_id)
        # Try to add a deduction for same triple
        ded = self._make_deduction(char, loc, ts_id)
        result = state.add_deduction(ded)
        assert result is False
        # The deduction should NOT be added
        assert len(state.current_project.deductions) == 0

    def test_add_deduction_rejects_duplicate_pending(self, state):
        """add_deduction returns False when triple already exists as a pending Deduction."""
        char, loc = self._setup_project(state)
        ts_id = self._get_ts_id(state, "14:00")
        # Add first deduction
        ded1 = self._make_deduction(char, loc, ts_id)
        result1 = state.add_deduction(ded1)
        assert result1 is True
        assert len(state.current_project.deductions) == 1
        # Try to add same triple again
        ded2 = self._make_deduction(char, loc, ts_id)
        result2 = state.add_deduction(ded2)
        assert result2 is False
        # Still only one deduction
        assert len(state.current_project.deductions) == 1

    def test_add_deduction_rejects_rejected_triple(self, state):
        """add_deduction returns False when triple was previously Rejected."""
        char, loc = self._setup_project(state)
        ts_id = self._get_ts_id(state, "14:00")
        # Add and reject a deduction
        ded = self._make_deduction(char, loc, ts_id)
        state.add_deduction(ded)
        state.reject_deduction(ded.id, "Test rejection")
        assert len(state.current_project.rejections) == 1
        # Try to add same triple again
        ded2 = self._make_deduction(char, loc, ts_id)
        result = state.add_deduction(ded2)
        assert result is False

    def test_add_deduction_accepts_new_triple(self, state):
        """add_deduction returns True and adds the deduction for a genuinely new triple."""
        char, loc = self._setup_project(state)
        ts_id = self._get_ts_id(state, "14:00")
        ded = self._make_deduction(char, loc, ts_id)
        result = state.add_deduction(ded)
        assert result is True
        assert len(state.current_project.deductions) == 1
        assert state.current_project.deductions[0].id == ded.id

    def test_accept_updates_fact_index(self, state):
        """Accepting a deduction moves triple from pending_index to fact_index."""
        char, loc = self._setup_project(state)
        ts_id = self._get_ts_id(state, "14:00")
        ded = self._make_deduction(char, loc, ts_id)
        state.add_deduction(ded)
        # Accept it
        fact = state.accept_deduction(ded.id)
        assert fact is not None
        # Triple should now be in fact_index
        triple = (char.id, loc.id, ts_id)
        assert triple in state._fact_index
        assert triple not in state._pending_index
        # Adding same triple again should return False
        ded2 = self._make_deduction(char, loc, ts_id)
        result = state.add_deduction(ded2)
        assert result is False

    def test_reject_updates_rejection_index(self, state):
        """Rejecting a deduction moves triple from pending_index to rejection_index."""
        char, loc = self._setup_project(state)
        ts_id = self._get_ts_id(state, "14:00")
        ded = self._make_deduction(char, loc, ts_id)
        state.add_deduction(ded)
        # Reject it
        rejection = state.reject_deduction(ded.id, "Test reason")
        assert rejection is not None
        # Triple should now be in rejection_index
        triple = (char.id, loc.id, ts_id)
        assert triple in state._rejection_index
        assert triple not in state._pending_index
        # Adding same triple again should return False
        ded2 = self._make_deduction(char, loc, ts_id)
        result = state.add_deduction(ded2)
        assert result is False

    def test_clear_pending_resets_pending_index(self, state):
        """clear_pending_deductions clears the pending index so triples can be re-added."""
        char, loc = self._setup_project(state)
        ts_id_14 = self._get_ts_id(state, "14:00")
        ts_id_15 = self._get_ts_id(state, "15:00")
        ded1 = self._make_deduction(char, loc, ts_id_14)
        ded2 = self._make_deduction(char, loc, ts_id_15)
        state.add_deduction(ded1)
        state.add_deduction(ded2)
        assert len(state.current_project.deductions) == 2
        # Clear pending
        removed = state.clear_pending_deductions()
        assert removed == 2
        assert len(state._pending_index) == 0
        # Re-adding should now succeed
        ded3 = self._make_deduction(char, loc, ts_id_14)
        result = state.add_deduction(ded3)
        assert result is True
        assert len(state.current_project.deductions) == 1

    def test_index_rebuilds_on_load(self, state):
        """Indexes are correctly rebuilt when loading an existing project."""
        char, loc = self._setup_project(state)
        project_id = state.current_project.id
        ts_id_14 = self._get_ts_id(state, "14:00")
        ts_id_15 = self._get_ts_id(state, "15:00")

        # Add a fact, a pending deduction, and a rejection
        state.add_fact(character_id=char.id, location_id=loc.id, time_slot=ts_id_14)
        ded_pending = self._make_deduction(char, loc, ts_id_15)
        state.add_deduction(ded_pending)
        # Create another character for rejection test
        char2 = state.add_character(name="Bob")
        ded_for_rejection = Deduction(
            character_id=char2.id,
            location_id=loc.id,
            time_slot=ts_id_14,
            confidence=ConfidenceLevel.low,
            reasoning="Will be rejected",
            status=DeductionStatus.pending,
        )
        state.add_deduction(ded_for_rejection)
        state.reject_deduction(ded_for_rejection.id, "Test rejection")

        # Reset state and reload
        state.current_project = None
        state._fact_index = set()
        state._pending_index = set()
        state._rejection_index = set()

        state.load_project(project_id)

        # Now indexes should be rebuilt
        # Fact triple (char.id, loc.id, ts_id_14) should be in fact_index
        assert (char.id, loc.id, ts_id_14) in state._fact_index
        # Pending triple (char.id, loc.id, ts_id_15) should be in pending_index
        assert (char.id, loc.id, ts_id_15) in state._pending_index
        # Rejection triple (char2.id, loc.id, ts_id_14) should be in rejection_index
        assert (char2.id, loc.id, ts_id_14) in state._rejection_index

        # Adding duplicates should fail
        ded_dup_fact = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts_id_14,
            confidence=ConfidenceLevel.medium,
            reasoning="dup",
        )
        assert state.add_deduction(ded_dup_fact) is False

        ded_dup_pending = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts_id_15,
            confidence=ConfidenceLevel.medium,
            reasoning="dup",
        )
        assert state.add_deduction(ded_dup_pending) is False

        ded_dup_rejection = Deduction(
            character_id=char2.id,
            location_id=loc.id,
            time_slot=ts_id_14,
            confidence=ConfidenceLevel.medium,
            reasoning="dup",
        )
        assert state.add_deduction(ded_dup_rejection) is False


class TestSaveScriptAnalysis:
    """Tests for the save_script_analysis method."""

    def test_save_script_analysis_success(self, state):
        """Saving analysis result should set it on the script and persist."""
        state.create_project(name="Test")
        script = state.add_script(raw_text="Some script text", title="Scene 1")
        result = {"characters_mentioned": [{"name": "Alice"}], "direct_facts": []}

        saved = state.save_script_analysis(script.id, result)
        assert saved is True
        assert script.analysis_result == result

        # Verify persisted to disk
        loaded = state.store.load_project(state.current_project.id)
        loaded_script = next(s for s in loaded.scripts if s.id == script.id)
        assert loaded_script.analysis_result == result

    def test_save_script_analysis_no_project(self, state):
        """Returns False when no project is loaded."""
        assert state.save_script_analysis("some-id", {}) is False

    def test_save_script_analysis_nonexistent_script(self, state):
        """Returns False for unknown script_id."""
        state.create_project(name="Test")
        assert state.save_script_analysis("nonexistent", {}) is False
