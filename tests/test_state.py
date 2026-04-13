"""Tests for the AppState manager."""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.models.puzzle import CharacterStatus, HintType, SourceType
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
        project = state.create_project(name="Test Mystery", description="A test")
        assert state.current_project is not None
        assert state.current_project.name == "Test Mystery"
        assert state.current_project.description == "A test"

    def test_create_project_with_time_slots(self, state):
        project = state.create_project(
            name="Test", time_slots=["14:00", "15:00", "16:00"]
        )
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

    def test_change_callback(self, state):
        calls = []
        state.on_change(lambda: calls.append(1))
        state.create_project(name="CB Test")
        assert len(calls) == 1
        state.save()  # save alone doesn't notify
        assert len(calls) == 1


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
        fact = state.add_fact(
            character_id=char.id, location_id=loc.id, time_slot="14:00"
        )
        removed = state.remove_fact(fact.id)
        assert removed is True
        assert len(state.current_project.facts) == 0

    def test_add_fact_no_project(self, state):
        with pytest.raises(ValueError, match="No project loaded"):
            state.add_fact(
                character_id="c1", location_id="l1", time_slot="14:00"
            )


class TestAppStateTimeSlots:
    def test_add_time_slot(self, state):
        state.create_project(name="Test")
        added = state.add_time_slot("14:00")
        assert added is True
        assert "14:00" in state.current_project.time_slots

    def test_add_duplicate_time_slot(self, state):
        state.create_project(name="Test", time_slots=["14:00"])
        added = state.add_time_slot("14:00")
        assert added is False

    def test_add_invalid_time_slot(self, state):
        state.create_project(name="Test")
        with pytest.raises(ValueError, match="HH:MM"):
            state.add_time_slot("invalid")

    def test_remove_time_slot(self, state):
        state.create_project(name="Test", time_slots=["14:00", "15:00"])
        removed = state.remove_time_slot("14:00")
        assert removed is True
        assert "14:00" not in state.current_project.time_slots
        assert "15:00" in state.current_project.time_slots

    def test_time_slots_sorted(self, state):
        state.create_project(name="Test")
        state.add_time_slot("16:00")
        state.add_time_slot("14:00")
        state.add_time_slot("15:00")
        assert state.current_project.time_slots == ["14:00", "15:00", "16:00"]


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


class TestAppStateCallbacks:
    def test_multiple_callbacks(self, state):
        calls_a = []
        calls_b = []
        state.on_change(lambda: calls_a.append(1))
        state.on_change(lambda: calls_b.append(1))
        state.create_project(name="Test")
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_callback_on_entity_add(self, state):
        state.create_project(name="Test")
        calls = []
        state.on_data_change(lambda: calls.append(1))
        state.add_character(name="Alice")
        state.add_location(name="Library")
        assert len(calls) == 2

    def test_bad_callback_does_not_break(self, state):
        """A failing callback should not prevent others from running."""
        calls = []

        def bad_cb():
            raise RuntimeError("bad callback")

        state.on_change(bad_cb)
        state.on_change(lambda: calls.append(1))
        state.create_project(name="Test")
        assert len(calls) == 1  # Second callback still ran

    def test_bad_data_callback_does_not_break(self, state):
        """A failing data callback should not prevent others from running."""
        state.create_project(name="Test")
        calls = []

        def bad_cb():
            raise RuntimeError("bad data callback")

        state.on_data_change(bad_cb)
        state.on_data_change(lambda: calls.append(1))
        state.add_character(name="Alice")
        assert len(calls) == 1  # Second callback still ran


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
