from __future__ import annotations

from pathlib import Path

import pytest

from src.models.puzzle import (
    Character,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    EntityKind,
    Fact,
    Hint,
    HintType,
    Location,
    Script,
    SourceType,
    TimeSlot,
)
from src.storage.json_repository import JsonRepository
from src.storage.json_store import JsonStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> JsonRepository:
    store = JsonStore(data_dir=tmp_path)
    return JsonRepository(store=store)


@pytest.fixture
def repo_with_project(tmp_path: Path) -> JsonRepository:
    store = JsonStore(data_dir=tmp_path)
    r = JsonRepository(store=store)
    r.create_project("Test Project", description="A test project")
    return r


def _make_deduction(char_id: str, loc_id: str, ts_id: str) -> Deduction:
    return Deduction(
        character_id=char_id,
        location_id=loc_id,
        time_slot=ts_id,
        confidence=ConfidenceLevel.high,
        reasoning="Test reasoning",
    )


# ===========================================================================
# VAL-REPO-001: Project lifecycle
# ===========================================================================


class TestProjectLifecycle:
    def test_create_project_returns_project_with_uuid(self, repo: JsonRepository) -> None:
        proj = repo.create_project("My Game")
        assert proj.id
        assert len(proj.id) > 8
        assert proj.name == "My Game"
        assert proj.characters == []
        assert proj.locations == []
        assert proj.facts == []
        assert proj.created_at is not None
        assert proj.updated_at is not None

    def test_create_project_sets_current_project(self, repo: JsonRepository) -> None:
        proj = repo.create_project("My Game")
        assert repo.current_project is not None
        assert repo.current_project.id == proj.id

    def test_load_project_roundtrip(self, repo: JsonRepository, tmp_path: Path) -> None:
        proj = repo.create_project("Round Trip Test", description="desc")
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("08:00", "Morning")
        repo.add_fact(char.id, loc.id, ts.id, SourceType.user_input)
        project_id = proj.id
        # Load fresh
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(project_id)
        loaded = repo2.current_project
        assert loaded is not None
        assert loaded.id == proj.id
        assert loaded.name == "Round Trip Test"
        assert len(loaded.characters) == 1
        assert loaded.characters[0].name == "Alice"
        assert len(loaded.locations) == 1
        assert len(loaded.time_slots) == 1
        assert len(loaded.facts) == 1

    def test_save_project_bumps_updated_at(self, repo_with_project: JsonRepository) -> None:
        import time

        proj = repo_with_project.current_project
        old_ts = proj.updated_at
        time.sleep(0.01)
        repo_with_project.save()
        assert proj.updated_at > old_ts

    def test_delete_project_removes_file(self, repo: JsonRepository, tmp_path: Path) -> None:
        proj = repo.create_project("To Delete")
        project_id = proj.id
        repo.delete_project(project_id)
        with pytest.raises(FileNotFoundError):
            JsonStore(data_dir=tmp_path).load_project(project_id)

    def test_delete_project_clears_current_if_matches(self, repo: JsonRepository) -> None:
        proj = repo.create_project("To Delete")
        repo.delete_project(proj.id)
        assert repo.current_project is None

    def test_delete_project_leaves_current_if_different(self, repo: JsonRepository) -> None:
        p1 = repo.create_project("P1")
        p2_store = JsonStore(data_dir=repo.store.data_dir)
        p2 = p2_store.create_project("P2")
        # current_project is p1; delete p2
        repo.delete_project(p2.id)
        assert repo.current_project is not None
        assert repo.current_project.id == p1.id

    def test_list_projects_returns_summaries(self, repo: JsonRepository) -> None:
        p1 = repo.create_project("P1")
        # Create a second project via the store directly
        repo.store.create_project("P2")
        summaries = repo.list_projects()
        ids = [s.id for s in summaries]
        assert p1.id in ids
        assert len(summaries) == 2

    def test_list_projects_empty_directory(self, tmp_path: Path) -> None:
        repo = JsonRepository(store=JsonStore(data_dir=tmp_path))
        assert repo.list_projects() == []

    def test_list_projects_skips_corrupt_files(self, repo: JsonRepository, tmp_path: Path) -> None:
        repo.create_project("Good")
        (tmp_path / "corrupt.json").write_text("not json", encoding="utf-8")
        summaries = repo.list_projects()
        assert len(summaries) == 1
        assert summaries[0].name == "Good"


# ===========================================================================
# VAL-REPO-002: Character CRUD
# ===========================================================================


class TestCharacterCRUD:
    def test_add_character_returns_character(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Bob")
        assert isinstance(char, Character)
        assert char.name == "Bob"
        assert char.id

    def test_add_character_persists(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        char = repo_with_project.add_character("Bob")
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert any(c.id == char.id for c in repo2.current_project.characters)

    def test_update_character_partial(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice", description="desc1")
        result = repo_with_project.update_character(char.id, name="Alice Updated")
        assert result is not None
        assert result.name == "Alice Updated"
        assert result.description == "desc1"  # untouched

    def test_update_character_missing_id_returns_none(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.update_character("nonexistent", name="X") is None

    def test_remove_character_returns_true(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Charlie")
        assert repo_with_project.remove_character(char.id) is True
        assert all(c.id != char.id for c in repo_with_project.current_project.characters)

    def test_remove_character_missing_returns_false(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.remove_character("nonexistent") is False

    def test_character_mutations_persist(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        char = repo_with_project.add_character("Dave")
        repo_with_project.update_character(char.id, name="David")
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        loaded_char = next(c for c in repo2.current_project.characters if c.id == char.id)
        assert loaded_char.name == "David"


# ===========================================================================
# VAL-REPO-003: Location CRUD
# ===========================================================================


class TestLocationCRUD:
    def test_add_location_returns_location(self, repo_with_project: JsonRepository) -> None:
        loc = repo_with_project.add_location("Kitchen")
        assert isinstance(loc, Location)
        assert loc.name == "Kitchen"
        assert loc.id

    def test_update_location_partial(self, repo_with_project: JsonRepository) -> None:
        loc = repo_with_project.add_location("Hall", description="main hall")
        result = repo_with_project.update_location(loc.id, name="Hallway")
        assert result is not None
        assert result.name == "Hallway"
        assert result.description == "main hall"  # untouched

    def test_update_location_missing_returns_none(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.update_location("bad", name="X") is None

    def test_remove_location_returns_true(self, repo_with_project: JsonRepository) -> None:
        loc = repo_with_project.add_location("Garden")
        assert repo_with_project.remove_location(loc.id) is True

    def test_remove_location_missing_returns_false(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.remove_location("bad") is False

    def test_location_persists_after_remove(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        loc = repo_with_project.add_location("Temp")
        repo_with_project.remove_location(loc.id)
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert all(lo2.id != loc.id for lo2 in repo2.current_project.locations)


# ===========================================================================
# VAL-REPO-004: TimeSlot management
# ===========================================================================


class TestTimeSlotManagement:
    def test_add_time_slot_validates_format(self, repo_with_project: JsonRepository) -> None:
        with pytest.raises(ValueError):
            repo_with_project.add_time_slot("9:00")  # missing leading zero
        with pytest.raises(ValueError):
            repo_with_project.add_time_slot("morning")

    def test_add_time_slot_returns_time_slot(self, repo_with_project: JsonRepository) -> None:
        ts = repo_with_project.add_time_slot("09:00")
        assert isinstance(ts, TimeSlot)
        assert ts.label == "09:00"
        assert ts.id

    def test_add_time_slot_dedup_same_label_same_desc(
        self, repo_with_project: JsonRepository
    ) -> None:
        repo_with_project.add_time_slot("10:00", "Morning")
        result = repo_with_project.add_time_slot("10:00", "Morning")
        assert result is None
        assert len(repo_with_project.current_project.time_slots) == 1

    def test_add_time_slot_allows_same_label_different_desc(
        self, repo_with_project: JsonRepository
    ) -> None:
        ts1 = repo_with_project.add_time_slot("10:00", "Day 1")
        ts2 = repo_with_project.add_time_slot("10:00", "Day 2")
        assert ts1 is not None
        assert ts2 is not None
        assert ts1.id != ts2.id

    def test_add_time_slot_auto_sort_order(self, repo_with_project: JsonRepository) -> None:
        ts1 = repo_with_project.add_time_slot("08:00")
        ts2 = repo_with_project.add_time_slot("12:00")
        assert ts2.sort_order > ts1.sort_order

    def test_remove_time_slot_by_id(self, repo_with_project: JsonRepository) -> None:
        ts = repo_with_project.add_time_slot("14:00")
        result = repo_with_project.remove_time_slot(ts.id)
        assert result is True
        assert len(repo_with_project.current_project.time_slots) == 0

    def test_remove_time_slot_missing_returns_false(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.remove_time_slot("nonexistent") is False

    def test_reorder_time_slot_swaps_neighbors(self, repo_with_project: JsonRepository) -> None:
        ts1 = repo_with_project.add_time_slot("08:00")
        ts2 = repo_with_project.add_time_slot("12:00")
        # Move ts2 up (direction=-1)
        result = repo_with_project.reorder_time_slot(ts2.id, -1)
        assert result is True
        slots = sorted(repo_with_project.current_project.time_slots, key=lambda t: t.sort_order)
        assert slots[0].id == ts2.id
        assert slots[1].id == ts1.id

    def test_reorder_time_slot_returns_false_at_boundary(
        self, repo_with_project: JsonRepository
    ) -> None:
        ts = repo_with_project.add_time_slot("08:00")
        # Already at top, move up should return False
        result = repo_with_project.reorder_time_slot(ts.id, -1)
        assert result is False

    def test_reorder_time_slot_missing_returns_false(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.reorder_time_slot("nonexistent", 1) is False

    def test_get_time_slot_by_id(self, repo_with_project: JsonRepository) -> None:
        ts = repo_with_project.add_time_slot("16:00", "Evening")
        found = repo_with_project.get_time_slot_by_id(ts.id)
        assert found is not None
        assert found.label == "16:00"

    def test_get_time_slot_by_id_missing_returns_none(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.get_time_slot_by_id("nonexistent") is None

    def test_get_time_slot_label_with_description(self, repo_with_project: JsonRepository) -> None:
        ts = repo_with_project.add_time_slot("09:00", "Morning")
        label = repo_with_project.get_time_slot_label(ts.id)
        assert label == "09:00 (Morning)"

    def test_get_time_slot_label_without_description(
        self, repo_with_project: JsonRepository
    ) -> None:
        ts = repo_with_project.add_time_slot("09:00")
        label = repo_with_project.get_time_slot_label(ts.id)
        assert label == "09:00"

    def test_get_time_slot_label_missing_returns_raw_id(
        self, repo_with_project: JsonRepository
    ) -> None:
        label = repo_with_project.get_time_slot_label("unknown-id")
        assert label == "unknown-id"

    def test_time_slot_persists(self, repo_with_project: JsonRepository, tmp_path: Path) -> None:
        ts = repo_with_project.add_time_slot("20:00", "Night")
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        loaded_ts = next((t for t in repo2.current_project.time_slots if t.id == ts.id), None)
        assert loaded_ts is not None
        assert loaded_ts.label == "20:00"
        assert loaded_ts.description == "Night"


# ===========================================================================
# VAL-REPO-005: Script CRUD
# ===========================================================================


class TestScriptCRUD:
    def test_add_script_returns_script(self, repo_with_project: JsonRepository) -> None:
        s = repo_with_project.add_script("Raw text here", title="Scene 1")
        assert isinstance(s, Script)
        assert s.raw_text == "Raw text here"
        assert s.title == "Scene 1"

    def test_add_script_auto_source_order(self, repo_with_project: JsonRepository) -> None:
        s1 = repo_with_project.add_script("Text 1")
        s2 = repo_with_project.add_script("Text 2")
        assert s1.metadata.source_order == 1
        assert s2.metadata.source_order == 2

    def test_update_script_partial(self, repo_with_project: JsonRepository) -> None:
        s = repo_with_project.add_script("Original", title="T1", user_notes="note1")
        result = repo_with_project.update_script(s.id, title="Updated")
        assert result is not None
        assert result.title == "Updated"
        assert result.raw_text == "Original"
        assert result.metadata.user_notes == "note1"  # untouched

    def test_update_script_missing_returns_none(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.update_script("bad", title="X") is None

    def test_save_script_analysis_returns_true(self, repo_with_project: JsonRepository) -> None:
        s = repo_with_project.add_script("Text")
        result = repo_with_project.save_script_analysis(s.id, {"key": "value"})
        assert result is True
        assert repo_with_project.current_project.scripts[0].analysis_result == {"key": "value"}

    def test_save_script_analysis_missing_script_returns_false(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.save_script_analysis("bad", {}) is False

    def test_save_script_analysis_no_project_returns_false(self, repo: JsonRepository) -> None:
        assert repo.save_script_analysis("any", {}) is False

    def test_remove_script_returns_true(self, repo_with_project: JsonRepository) -> None:
        s = repo_with_project.add_script("Text")
        assert repo_with_project.remove_script(s.id) is True

    def test_remove_script_missing_returns_false(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.remove_script("bad") is False

    def test_script_analysis_survives_reload(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        s = repo_with_project.add_script("Text")
        repo_with_project.save_script_analysis(s.id, {"chars": ["Alice"]})
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        loaded_s = repo2.current_project.scripts[0]
        assert loaded_s.analysis_result == {"chars": ["Alice"]}


# ===========================================================================
# VAL-REPO-006: Fact add/remove with dedup-index side effects
# ===========================================================================


class TestFactManagement:
    def test_add_fact_returns_fact(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        fact = repo_with_project.add_fact(char.id, loc.id, ts.id)
        assert isinstance(fact, Fact)
        assert fact.character_id == char.id

    def test_add_fact_updates_fact_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        repo_with_project.add_fact(char.id, loc.id, ts.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.fact_index

    def test_add_fact_blocks_add_deduction(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        repo_with_project.add_fact(char.id, loc.id, ts.id)
        ded = _make_deduction(char.id, loc.id, ts.id)
        result = repo_with_project.add_deduction(ded)
        assert result is False

    def test_remove_fact_returns_true(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        fact = repo_with_project.add_fact(char.id, loc.id, ts.id)
        result = repo_with_project.remove_fact(fact.id)
        assert result is True
        assert len(repo_with_project.current_project.facts) == 0

    def test_remove_fact_clears_fact_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        fact = repo_with_project.add_fact(char.id, loc.id, ts.id)
        repo_with_project.remove_fact(fact.id)
        triple = (char.id, loc.id, ts.id)
        assert triple not in repo_with_project._cache.fact_index

    def test_remove_fact_unblocks_add_deduction(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        fact = repo_with_project.add_fact(char.id, loc.id, ts.id)
        repo_with_project.remove_fact(fact.id)
        ded = _make_deduction(char.id, loc.id, ts.id)
        result = repo_with_project.add_deduction(ded)
        assert result is True

    def test_remove_fact_missing_returns_false(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.remove_fact("nonexistent") is False


# ===========================================================================
# VAL-REPO-007: Deduction lifecycle
# ===========================================================================


class TestDeductionLifecycle:
    def test_add_deduction_returns_true(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        assert repo_with_project.add_deduction(ded) is True

    def test_add_deduction_blocked_by_fact_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        repo_with_project.add_fact(char.id, loc.id, ts.id)
        ded = _make_deduction(char.id, loc.id, ts.id)
        assert repo_with_project.add_deduction(ded) is False

    def test_add_deduction_blocked_by_pending_index(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded1 = _make_deduction(char.id, loc.id, ts.id)
        ded2 = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded1)
        assert repo_with_project.add_deduction(ded2) is False

    def test_add_deduction_blocked_by_rejection_index(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        ded2 = _make_deduction(char.id, loc.id, ts.id)
        assert repo_with_project.add_deduction(ded2) is False

    def test_accept_deduction_creates_fact(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        fact = repo_with_project.accept_deduction(ded.id)
        assert fact is not None
        assert fact.source_type == SourceType.ai_deduction
        assert fact.from_deduction_id == ded.id

    def test_accept_deduction_moves_triple_to_fact_index(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.accept_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        assert triple not in repo_with_project._cache.pending_index
        assert triple in repo_with_project._cache.fact_index

    def test_accept_deduction_sets_status_accepted(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.accept_deduction(ded.id)
        assert ded.status == DeductionStatus.accepted
        assert ded.resolved_at is not None

    def test_accept_deduction_missing_returns_none(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.accept_deduction("nonexistent") is None

    def test_reject_deduction_creates_rejection(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        rejection = repo_with_project.reject_deduction(ded.id)
        assert rejection is not None
        assert rejection.from_deduction_id == ded.id

    def test_reject_deduction_default_reason(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        rejection = repo_with_project.reject_deduction(ded.id)
        assert rejection.reason == "\u7528\u6237\u62d2\u7edd"

    def test_reject_deduction_custom_reason(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        rejection = repo_with_project.reject_deduction(ded.id, reason="Not convincing")
        assert rejection.reason == "Not convincing"

    def test_reject_deduction_moves_triple_to_rejection_index(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        assert triple not in repo_with_project._cache.pending_index
        assert triple in repo_with_project._cache.rejection_index

    def test_reject_deduction_missing_returns_none(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.reject_deduction("nonexistent") is None

    def test_get_pending_deductions_returns_only_pending(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts1 = repo_with_project.add_time_slot("09:00")
        ts2 = repo_with_project.add_time_slot("10:00")
        ts3 = repo_with_project.add_time_slot("11:00")
        ded1 = _make_deduction(char.id, loc.id, ts1.id)
        ded2 = _make_deduction(char.id, loc.id, ts2.id)
        ded3 = _make_deduction(char.id, loc.id, ts3.id)
        repo_with_project.add_deduction(ded1)
        repo_with_project.add_deduction(ded2)
        repo_with_project.add_deduction(ded3)
        repo_with_project.accept_deduction(ded1.id)
        pending = repo_with_project.get_pending_deductions()
        assert len(pending) == 2
        ids = [d.id for d in pending]
        assert ded2.id in ids
        assert ded3.id in ids

    def test_clear_pending_deductions_removes_all_pending(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts1 = repo_with_project.add_time_slot("09:00")
        ts2 = repo_with_project.add_time_slot("10:00")
        ded1 = _make_deduction(char.id, loc.id, ts1.id)
        ded2 = _make_deduction(char.id, loc.id, ts2.id)
        repo_with_project.add_deduction(ded1)
        repo_with_project.add_deduction(ded2)
        count = repo_with_project.clear_pending_deductions()
        assert count == 2
        assert repo_with_project.get_pending_deductions() == []
        assert len(repo_with_project._cache.pending_index) == 0


# ===========================================================================
# VAL-REPO-008: Character/Location merge with alias dedup
# ===========================================================================


class TestMerge:
    def test_merge_character_adds_alias(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        result = repo_with_project.merge_character("Ali", char.id)
        assert result is not None
        assert "Ali" in result.aliases

    def test_merge_character_skips_if_same_as_name(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        result = repo_with_project.merge_character("alice", char.id)  # case-insensitive
        assert result is not None
        assert "alice" not in result.aliases

    def test_merge_character_skips_existing_alias(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice", aliases=["Ali"])
        result = repo_with_project.merge_character("Ali", char.id)
        assert result.aliases.count("Ali") == 1  # no duplicate

    def test_merge_character_missing_target_returns_none(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.merge_character("Ali", "nonexistent") is None

    def test_merge_character_persists(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        char = repo_with_project.add_character("Bob")
        repo_with_project.merge_character("Robert", char.id)
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        loaded = next(c for c in repo2.current_project.characters if c.id == char.id)
        assert "Robert" in loaded.aliases

    def test_merge_location_adds_alias(self, repo_with_project: JsonRepository) -> None:
        loc = repo_with_project.add_location("Library")
        result = repo_with_project.merge_location("Lib", loc.id)
        assert result is not None
        assert "Lib" in result.aliases

    def test_merge_location_missing_target_returns_none(
        self, repo_with_project: JsonRepository
    ) -> None:
        assert repo_with_project.merge_location("X", "nonexistent") is None


# ===========================================================================
# VAL-REPO-009: Hint and IgnoredEntity operations
# ===========================================================================


class TestHintAndIgnoredEntity:
    def test_add_hint_returns_hint(self, repo_with_project: JsonRepository) -> None:
        hint = repo_with_project.add_hint(HintType.rule, "Alice was there")
        assert isinstance(hint, Hint)
        assert hint.type == HintType.rule
        assert hint.content == "Alice was there"

    def test_remove_hint_returns_true(self, repo_with_project: JsonRepository) -> None:
        hint = repo_with_project.add_hint(HintType.hint, "clue")
        assert repo_with_project.remove_hint(hint.id) is True

    def test_remove_hint_missing_returns_false(self, repo_with_project: JsonRepository) -> None:
        assert repo_with_project.remove_hint("bad") is False

    def test_ignore_entity_dedup_case_insensitive(self, repo_with_project: JsonRepository) -> None:
        e1 = repo_with_project.ignore_entity(EntityKind.character, "Alice")
        e2 = repo_with_project.ignore_entity(EntityKind.character, "alice")
        assert e1.id == e2.id
        assert len(repo_with_project.current_project.ignored_entities) == 1

    def test_ignore_entity_strips_whitespace(self, repo_with_project: JsonRepository) -> None:
        e1 = repo_with_project.ignore_entity(EntityKind.character, "  Bob  ")
        assert e1.name == "Bob"

    def test_ignore_entity_kind_specific(self, repo_with_project: JsonRepository) -> None:
        repo_with_project.ignore_entity(EntityKind.character, "Alice")
        repo_with_project.ignore_entity(EntityKind.location, "Alice")
        assert len(repo_with_project.current_project.ignored_entities) == 2

    def test_is_entity_ignored_true(self, repo_with_project: JsonRepository) -> None:
        repo_with_project.ignore_entity(EntityKind.character, "Alice")
        assert repo_with_project.is_entity_ignored(EntityKind.character, "alice") is True
        assert repo_with_project.is_entity_ignored(EntityKind.character, "  Alice  ") is True

    def test_is_entity_ignored_false_for_other_kind(
        self, repo_with_project: JsonRepository
    ) -> None:
        repo_with_project.ignore_entity(EntityKind.character, "Alice")
        assert repo_with_project.is_entity_ignored(EntityKind.location, "Alice") is False

    def test_is_entity_ignored_no_project_returns_false(self, repo: JsonRepository) -> None:
        assert repo.is_entity_ignored(EntityKind.character, "Alice") is False


# ===========================================================================
# VAL-REPO-010: No-project guard behavior
# ===========================================================================


class TestNoProjectGuard:
    def test_add_character_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.add_character("Alice")

    def test_update_character_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.update_character("some-id", name="X")

    def test_remove_character_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.remove_character("some-id")

    def test_add_location_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.add_location("Kitchen")

    def test_update_location_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.update_location("some-id", name="X")

    def test_remove_location_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.remove_location("some-id")

    def test_add_script_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.add_script("text")

    def test_update_script_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.update_script("some-id", title="X")

    def test_remove_script_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.remove_script("some-id")

    def test_add_fact_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.add_fact("c", "l", "t")

    def test_remove_fact_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.remove_fact("some-id")

    def test_add_time_slot_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.add_time_slot("08:00")

    def test_remove_time_slot_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.remove_time_slot("some-id")

    def test_reorder_time_slot_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.reorder_time_slot("some-id", 1)

    def test_add_hint_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.add_hint(HintType.hint, "content")

    def test_remove_hint_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.remove_hint("some-id")

    def test_ignore_entity_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.ignore_entity(EntityKind.character, "Alice")

    def test_merge_character_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.merge_character("X", "some-id")

    def test_merge_location_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.merge_location("X", "some-id")

    def test_add_deduction_raises_without_project(self, repo: JsonRepository) -> None:
        ded = Deduction(
            character_id="c",
            location_id="l",
            time_slot="t",
            confidence=ConfidenceLevel.high,
            reasoning="test",
        )
        with pytest.raises(ValueError, match="No project loaded"):
            repo.add_deduction(ded)

    def test_accept_deduction_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.accept_deduction("some-id")

    def test_reject_deduction_raises_without_project(self, repo: JsonRepository) -> None:
        with pytest.raises(ValueError, match="No project loaded"):
            repo.reject_deduction("some-id")

    # Read-only methods return safe defaults
    def test_get_time_slot_by_id_no_project_returns_none(self, repo: JsonRepository) -> None:
        assert repo.get_time_slot_by_id("any") is None

    def test_get_time_slot_label_no_project_returns_raw_id(self, repo: JsonRepository) -> None:
        assert repo.get_time_slot_label("some-raw-id") == "some-raw-id"

    def test_get_pending_deductions_no_project_returns_empty(self, repo: JsonRepository) -> None:
        assert repo.get_pending_deductions() == []

    def test_clear_pending_deductions_no_project_returns_zero(self, repo: JsonRepository) -> None:
        assert repo.clear_pending_deductions() == 0

    def test_save_script_analysis_no_project_returns_false(self, repo: JsonRepository) -> None:
        assert repo.save_script_analysis("any", {}) is False


# ===========================================================================
# VAL-REPO-011: create_project sets current_project and rebuilds indexes
# ===========================================================================


class TestCreateProjectSetsCurrentProject:
    def test_create_project_immediately_usable(self, repo: JsonRepository) -> None:
        repo.create_project("Immediate")
        # Should be able to add without loading
        char = repo.add_character("Alice")
        assert char is not None
        assert len(repo.current_project.characters) == 1

    def test_create_project_indexes_populated(self, repo: JsonRepository) -> None:
        repo.create_project("Test")
        char = repo.add_character("Alice")
        loc = repo.add_location("Lib")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        # Indexes should be populated immediately
        assert char.id in repo._cache.char_by_id
        assert loc.id in repo._cache.loc_by_id
        assert ts.id in repo._cache.ts_by_id
        assert (char.id, loc.id, ts.id) in repo._cache.fact_index


# ===========================================================================
# VAL-REPO-012: delete_project conditionally clears current_project
# ===========================================================================


class TestDeleteProjectConditional:
    def test_delete_current_project_clears_it(self, repo: JsonRepository) -> None:
        proj = repo.create_project("Current")
        repo.delete_project(proj.id)
        assert repo.current_project is None

    def test_delete_other_project_leaves_current(self, repo: JsonRepository) -> None:
        proj1 = repo.create_project("P1")
        # Create p2 directly via store
        p2 = repo.store.create_project("P2")
        repo.delete_project(p2.id)
        assert repo.current_project is not None
        assert repo.current_project.id == proj1.id


# ===========================================================================
# VAL-REPO-013: Deduction preserved in list after accept/reject with timestamps
# ===========================================================================


class TestDeductionPreservedAfterResolve:
    def test_accept_deduction_preserved_in_list(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.accept_deduction(ded.id)
        all_deds = repo_with_project.current_project.deductions
        found = next((d for d in all_deds if d.id == ded.id), None)
        assert found is not None
        assert found.status == DeductionStatus.accepted
        assert found.resolved_at is not None

    def test_reject_deduction_preserved_in_list(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        all_deds = repo_with_project.current_project.deductions
        found = next((d for d in all_deds if d.id == ded.id), None)
        assert found is not None
        assert found.status == DeductionStatus.rejected
        assert found.resolved_at is not None

    def test_accepted_fact_has_from_deduction_id(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        fact = repo_with_project.accept_deduction(ded.id)
        assert fact.from_deduction_id == ded.id

    def test_rejected_rejection_has_default_reason(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        rejection = repo_with_project.reject_deduction(ded.id, reason="")
        assert rejection.reason == "\u7528\u6237\u62d2\u7edd"


# ===========================================================================
# VAL-REPO-014: save() bumps updated_at timestamp
# ===========================================================================


class TestSaveBumpsUpdatedAt:
    def test_save_bumps_updated_at(self, repo_with_project: JsonRepository) -> None:
        import time

        proj = repo_with_project.current_project
        old_ts = proj.updated_at
        time.sleep(0.01)
        repo_with_project.save()
        assert proj.updated_at > old_ts

    def test_updated_at_persists_to_disk(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        import time

        time.sleep(0.01)
        repo_with_project.save()
        proj_id = repo_with_project.current_project.id
        updated = repo_with_project.current_project.updated_at
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        # The timestamps should be equal (both from disk)
        assert repo2.current_project.updated_at == updated


# ===========================================================================
# VAL-REPO-015: Legacy JSON migration
# ===========================================================================


class TestLegacyMigration:
    def test_legacy_string_time_slots_migrate(self, tmp_path: Path) -> None:
        import json
        from uuid import uuid4

        proj_id = str(uuid4())
        legacy = {
            "id": proj_id,
            "name": "Legacy",
            "description": None,
            "time_slots": ["08:00", "12:00"],
            "characters": [],
            "locations": [],
            "scripts": [],
            "facts": [],
            "rejections": [],
            "deductions": [],
            "hints": [],
            "ignored_entities": [],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
        (tmp_path / f"{proj_id}.json").write_text(json.dumps(legacy), encoding="utf-8")
        repo = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo.load_project(proj_id)
        proj = repo.current_project
        assert len(proj.time_slots) == 2
        for ts in proj.time_slots:
            assert isinstance(ts, TimeSlot)
            assert ts.id
            assert ts.label in ("08:00", "12:00")

    def test_legacy_migration_updates_fact_references(self, tmp_path: Path) -> None:
        import json
        from uuid import uuid4

        proj_id = str(uuid4())
        char_id = str(uuid4())
        loc_id = str(uuid4())
        legacy = {
            "id": proj_id,
            "name": "Legacy",
            "description": None,
            "time_slots": ["08:00"],
            "characters": [
                {
                    "id": char_id,
                    "name": "Alice",
                    "aliases": [],
                    "status": "confirmed",
                    "created_at": "2024-01-01T00:00:00",
                }
            ],
            "locations": [
                {"id": loc_id, "name": "Lib", "aliases": [], "created_at": "2024-01-01T00:00:00"}
            ],
            "scripts": [],
            "facts": [
                {
                    "id": str(uuid4()),
                    "character_id": char_id,
                    "location_id": loc_id,
                    "time_slot": "08:00",
                    "source_type": "user_input",
                    "source_script_ids": [],
                    "confirmed_at": "2024-01-01T00:00:00",
                }
            ],
            "rejections": [],
            "deductions": [],
            "hints": [],
            "ignored_entities": [],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
        (tmp_path / f"{proj_id}.json").write_text(json.dumps(legacy), encoding="utf-8")
        repo = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo.load_project(proj_id)
        proj = repo.current_project
        ts_id = proj.time_slots[0].id
        # Fact should reference the new ts_id
        assert proj.facts[0].time_slot == ts_id


# ===========================================================================
# VAL-REPO-016: Multi-project isolation
# ===========================================================================


class TestMultiProjectIsolation:
    def test_add_to_p1_does_not_affect_p2(self, repo: JsonRepository, tmp_path: Path) -> None:
        repo.create_project("P1")
        p2 = repo.store.create_project("P2")
        p2_id = p2.id
        # Add character to P1 (currently loaded)
        repo.add_character("Alice")
        # Load P2 and check
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(p2_id)
        assert len(repo2.current_project.characters) == 0

    def test_p1_data_preserved_when_loading_p2(self, repo: JsonRepository, tmp_path: Path) -> None:
        p1 = repo.create_project("P1")
        repo.add_character("Alice")
        p1_id = p1.id
        p2 = repo.store.create_project("P2")
        # Load P2 in same repo (changes current_project)
        repo.load_project(p2.id)
        # Now reload P1 and verify Alice is still there
        repo.load_project(p1_id)
        assert any(c.name == "Alice" for c in repo.current_project.characters)


# ===========================================================================
# Index consistency (VAL-IDX tests through Repository)
# ===========================================================================


class TestIndexConsistency:
    def test_char_by_id_updated_on_add(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        assert char.id in repo_with_project._cache.char_by_id

    def test_char_by_id_cleaned_on_remove(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        repo_with_project.remove_character(char.id)
        assert char.id not in repo_with_project._cache.char_by_id

    def test_char_by_name_updated_on_add(self, repo_with_project: JsonRepository) -> None:
        repo_with_project.add_character("Alice")
        assert "alice" in repo_with_project._cache.char_by_name

    def test_char_by_name_cleaned_on_remove(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        repo_with_project.remove_character(char.id)
        assert "alice" not in repo_with_project._cache.char_by_name

    def test_loc_by_id_updated_on_add(self, repo_with_project: JsonRepository) -> None:
        loc = repo_with_project.add_location("Library")
        assert loc.id in repo_with_project._cache.loc_by_id

    def test_ts_by_id_updated_on_add(self, repo_with_project: JsonRepository) -> None:
        ts = repo_with_project.add_time_slot("09:00")
        assert ts.id in repo_with_project._cache.ts_by_id

    def test_rebuild_indexes_after_load(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        repo_with_project.add_fact(char.id, loc.id, ts.id)
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert char.id in repo2._cache.char_by_id
        assert loc.id in repo2._cache.loc_by_id
        assert ts.id in repo2._cache.ts_by_id
        assert (char.id, loc.id, ts.id) in repo2._cache.fact_index

    def test_pending_index_updated_on_add_deduction(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        assert (char.id, loc.id, ts.id) in repo_with_project._cache.pending_index

    def test_pending_index_emptied_on_clear(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.clear_pending_deductions()
        assert len(repo_with_project._cache.pending_index) == 0

    def test_rejection_index_updated_on_reject(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        assert (char.id, loc.id, ts.id) in repo_with_project._cache.rejection_index

    def test_fresh_create_has_empty_indexes(self, repo: JsonRepository) -> None:
        repo.create_project("Empty")
        assert len(repo._cache.char_by_id) == 0
        assert len(repo._cache.fact_index) == 0
        assert len(repo._cache.pending_index) == 0


# ===========================================================================
# Cross-area / integration tests
# ===========================================================================


class TestCrossAreaIntegration:
    def test_full_deduction_lifecycle(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        assert repo_with_project.add_deduction(ded) is True
        # Pending
        assert (char.id, loc.id, ts.id) in repo_with_project._cache.pending_index
        # Accept
        fact = repo_with_project.accept_deduction(ded.id)
        assert fact is not None
        assert (char.id, loc.id, ts.id) in repo_with_project._cache.fact_index
        assert (char.id, loc.id, ts.id) not in repo_with_project._cache.pending_index
        # Reload verifies persistence
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert len(repo2.current_project.facts) == 1
        assert repo2.current_project.facts[0].from_deduction_id == ded.id

    def test_rejection_blocks_readd(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Lib")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        ded2 = _make_deduction(char.id, loc.id, ts.id)
        assert repo_with_project.add_deduction(ded2) is False

    def test_save_reload_preserves_all_data(
        self, repo_with_project: JsonRepository, tmp_path: Path
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00", "Morning")
        repo_with_project.add_fact(char.id, loc.id, ts.id, SourceType.user_input, "evidence")
        # Rejected to test rejection persistence
        repo_with_project.add_fact(
            char.id, loc.id, ts.id + "_dummy"
        )  # won't work without valid ts but that is fine
        repo_with_project.add_hint(HintType.constraint, "Only one location")
        repo_with_project.ignore_entity(EntityKind.character, "Ghost")
        proj_id = repo_with_project.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        p = repo2.current_project
        assert len(p.characters) == 1
        assert p.characters[0].name == "Alice"
        assert len(p.locations) == 1
        assert len(p.time_slots) == 1
        assert p.time_slots[0].description == "Morning"
        assert len(p.hints) == 1
        assert len(p.ignored_entities) == 1


# ===========================================================================
# CRUD remove + dedup index consistency tests
# ===========================================================================


class TestRemoveEntityDedupIndexClean:
    """After removing a character/location/time_slot with dependent
    facts/deductions/rejections, the dedup indexes (fact_index, pending_index,
    rejection_index) must be clean — no stale triples remain."""

    def test_remove_character_cleans_fact_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        repo_with_project.add_fact(char.id, loc.id, ts.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.fact_index
        repo_with_project.remove_character(char.id)
        assert triple not in repo_with_project._cache.fact_index

    def test_remove_character_cleans_pending_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.pending_index
        repo_with_project.remove_character(char.id)
        assert triple not in repo_with_project._cache.pending_index

    def test_remove_character_cleans_rejection_index(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.rejection_index
        repo_with_project.remove_character(char.id)
        assert triple not in repo_with_project._cache.rejection_index

    def test_remove_location_cleans_fact_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        repo_with_project.add_fact(char.id, loc.id, ts.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.fact_index
        repo_with_project.remove_location(loc.id)
        assert triple not in repo_with_project._cache.fact_index

    def test_remove_location_cleans_pending_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.pending_index
        repo_with_project.remove_location(loc.id)
        assert triple not in repo_with_project._cache.pending_index

    def test_remove_location_cleans_rejection_index(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.rejection_index
        repo_with_project.remove_location(loc.id)
        assert triple not in repo_with_project._cache.rejection_index

    def test_remove_timeslot_cleans_fact_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        repo_with_project.add_fact(char.id, loc.id, ts.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.fact_index
        repo_with_project.remove_time_slot(ts.id)
        assert triple not in repo_with_project._cache.fact_index

    def test_remove_timeslot_cleans_pending_index(self, repo_with_project: JsonRepository) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.pending_index
        repo_with_project.remove_time_slot(ts.id)
        assert triple not in repo_with_project._cache.pending_index

    def test_remove_timeslot_cleans_rejection_index(
        self, repo_with_project: JsonRepository
    ) -> None:
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts = repo_with_project.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo_with_project.add_deduction(ded)
        repo_with_project.reject_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo_with_project._cache.rejection_index
        repo_with_project.remove_time_slot(ts.id)
        assert triple not in repo_with_project._cache.rejection_index

    def test_remove_character_with_mixed_records_cleans_all_indexes(
        self, repo_with_project: JsonRepository
    ) -> None:
        """Character with facts, pending deductions, and rejections — all cleaned."""
        char = repo_with_project.add_character("Alice")
        loc = repo_with_project.add_location("Library")
        ts1 = repo_with_project.add_time_slot("09:00")
        ts2 = repo_with_project.add_time_slot("10:00")
        ts3 = repo_with_project.add_time_slot("11:00")
        # Fact
        repo_with_project.add_fact(char.id, loc.id, ts1.id)
        # Pending deduction
        ded_pending = _make_deduction(char.id, loc.id, ts2.id)
        repo_with_project.add_deduction(ded_pending)
        # Rejected deduction
        ded_reject = _make_deduction(char.id, loc.id, ts3.id)
        repo_with_project.add_deduction(ded_reject)
        repo_with_project.reject_deduction(ded_reject.id)

        triple_fact = (char.id, loc.id, ts1.id)
        triple_pending = (char.id, loc.id, ts2.id)
        triple_rejected = (char.id, loc.id, ts3.id)

        assert triple_fact in repo_with_project._cache.fact_index
        assert triple_pending in repo_with_project._cache.pending_index
        assert triple_rejected in repo_with_project._cache.rejection_index

        repo_with_project.remove_character(char.id)

        assert triple_fact not in repo_with_project._cache.fact_index
        assert triple_pending not in repo_with_project._cache.pending_index
        assert triple_rejected not in repo_with_project._cache.rejection_index
