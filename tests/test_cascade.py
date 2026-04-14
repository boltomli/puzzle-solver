"""Tests for cascade delete logic in JsonRepository.

Covers VAL-CASCADE-001 through VAL-CASCADE-008.
Write tests FIRST (TDD), then implement cascade behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models.puzzle import (
    ConfidenceLevel,
    Deduction,
)
from src.storage.json_repository import JsonRepository
from src.storage.json_store import JsonStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> JsonRepository:
    store = JsonStore(data_dir=tmp_path)
    r = JsonRepository(store=store)
    r.create_project("Cascade Test")
    return r


def _make_deduction(
    char_id: str,
    loc_id: str,
    ts_id: str,
    *,
    supporting_script_ids: list[str] | None = None,
) -> Deduction:
    return Deduction(
        character_id=char_id,
        location_id=loc_id,
        time_slot=ts_id,
        confidence=ConfidenceLevel.high,
        reasoning="Test reasoning",
        supporting_script_ids=supporting_script_ids or [],
    )


# ===========================================================================
# VAL-CASCADE-001: Delete Character cascades to facts, deductions, rejections
# ===========================================================================


class TestCascadeDeleteCharacter:
    """Removing a character deletes all Fact, Deduction, and Rejection records
    referencing that character's ID. Records referencing other characters are
    unaffected."""

    def test_cascade_deletes_facts_referencing_character(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        repo.remove_character(char.id)
        assert len(repo.current_project.facts) == 0

    def test_cascade_deletes_deductions_referencing_character(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.remove_character(char.id)
        assert len(repo.current_project.deductions) == 0

    def test_cascade_deletes_rejections_referencing_character(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        repo.remove_character(char.id)
        assert len(repo.current_project.rejections) == 0

    def test_cascade_preserves_unrelated_facts(self, repo: JsonRepository) -> None:
        alice = repo.add_character("Alice")
        bob = repo.add_character("Bob")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(alice.id, loc.id, ts.id)
        repo.add_fact(bob.id, loc.id, ts.id)
        repo.remove_character(alice.id)
        assert len(repo.current_project.facts) == 1
        assert repo.current_project.facts[0].character_id == bob.id

    def test_cascade_preserves_unrelated_deductions(self, repo: JsonRepository) -> None:
        alice = repo.add_character("Alice")
        bob = repo.add_character("Bob")
        loc = repo.add_location("Library")
        ts1 = repo.add_time_slot("09:00")
        ts2 = repo.add_time_slot("10:00")
        ded_alice = _make_deduction(alice.id, loc.id, ts1.id)
        ded_bob = _make_deduction(bob.id, loc.id, ts2.id)
        repo.add_deduction(ded_alice)
        repo.add_deduction(ded_bob)
        repo.remove_character(alice.id)
        assert len(repo.current_project.deductions) == 1
        assert repo.current_project.deductions[0].character_id == bob.id

    def test_cascade_preserves_unrelated_rejections(self, repo: JsonRepository) -> None:
        alice = repo.add_character("Alice")
        bob = repo.add_character("Bob")
        loc = repo.add_location("Library")
        ts1 = repo.add_time_slot("09:00")
        ts2 = repo.add_time_slot("10:00")
        ded_alice = _make_deduction(alice.id, loc.id, ts1.id)
        ded_bob = _make_deduction(bob.id, loc.id, ts2.id)
        repo.add_deduction(ded_alice)
        repo.add_deduction(ded_bob)
        repo.reject_deduction(ded_alice.id)
        repo.reject_deduction(ded_bob.id)
        repo.remove_character(alice.id)
        assert len(repo.current_project.rejections) == 1
        assert repo.current_project.rejections[0].character_id == bob.id

    def test_cascade_deletes_accepted_deductions_for_character(self, repo: JsonRepository) -> None:
        """Accepted deductions referencing the character should also be removed."""
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.accept_deduction(ded.id)
        # Now facts and accepted deduction both reference char
        repo.remove_character(char.id)
        assert len(repo.current_project.deductions) == 0
        assert len(repo.current_project.facts) == 0

    def test_cascade_deletes_multiple_facts_for_character(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc1 = repo.add_location("Library")
        loc2 = repo.add_location("Garden")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc1.id, ts.id)
        repo.add_fact(char.id, loc2.id, ts.id)
        repo.remove_character(char.id)
        assert len(repo.current_project.facts) == 0


# ===========================================================================
# VAL-CASCADE-002: Delete Character cleans script metadata
# ===========================================================================


class TestCascadeDeleteCharacterScriptMetadata:
    """Removing a character removes its name from every
    Script.metadata.characters_mentioned list."""

    def test_removes_name_from_characters_mentioned(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        script = repo.add_script("Some text")
        script.metadata.characters_mentioned = ["Alice", "Bob"]
        repo.save()
        repo.remove_character(char.id)
        assert "Alice" not in repo.current_project.scripts[0].metadata.characters_mentioned
        assert "Bob" in repo.current_project.scripts[0].metadata.characters_mentioned

    def test_removes_from_multiple_scripts(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        s1 = repo.add_script("Text 1")
        s2 = repo.add_script("Text 2")
        s1.metadata.characters_mentioned = ["Alice", "Charlie"]
        s2.metadata.characters_mentioned = ["Alice"]
        repo.save()
        repo.remove_character(char.id)
        assert "Alice" not in repo.current_project.scripts[0].metadata.characters_mentioned
        assert "Alice" not in repo.current_project.scripts[1].metadata.characters_mentioned

    def test_no_scripts_no_error(self, repo: JsonRepository) -> None:
        """Character with no script references deletes cleanly."""
        char = repo.add_character("Alice")
        repo.remove_character(char.id)
        assert len(repo.current_project.characters) == 0

    def test_name_not_in_any_script_no_error(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        script = repo.add_script("Text")
        script.metadata.characters_mentioned = ["Bob"]
        repo.save()
        repo.remove_character(char.id)
        assert repo.current_project.scripts[0].metadata.characters_mentioned == ["Bob"]


# ===========================================================================
# VAL-CASCADE-003: Delete Location cascades to facts, deductions, rejections
# ===========================================================================


class TestCascadeDeleteLocation:
    """Same cascade contract as VAL-CASCADE-001 but for locations
    (matching on location_id)."""

    def test_cascade_deletes_facts_referencing_location(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        repo.remove_location(loc.id)
        assert len(repo.current_project.facts) == 0

    def test_cascade_deletes_deductions_referencing_location(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.remove_location(loc.id)
        assert len(repo.current_project.deductions) == 0

    def test_cascade_deletes_rejections_referencing_location(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        repo.remove_location(loc.id)
        assert len(repo.current_project.rejections) == 0

    def test_cascade_preserves_unrelated_records(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        lib = repo.add_location("Library")
        garden = repo.add_location("Garden")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, lib.id, ts.id)
        repo.add_fact(char.id, garden.id, ts.id)
        repo.remove_location(lib.id)
        assert len(repo.current_project.facts) == 1
        assert repo.current_project.facts[0].location_id == garden.id

    def test_cascade_deletes_accepted_deductions_for_location(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.accept_deduction(ded.id)
        repo.remove_location(loc.id)
        assert len(repo.current_project.deductions) == 0
        assert len(repo.current_project.facts) == 0


# ===========================================================================
# VAL-CASCADE-004: Delete TimeSlot cascades to facts, deductions, rejections
# ===========================================================================


class TestCascadeDeleteTimeSlot:
    """Same cascade contract as VAL-CASCADE-001 but for time slots
    (matching on time_slot field)."""

    def test_cascade_deletes_facts_referencing_timeslot(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        repo.remove_time_slot(ts.id)
        assert len(repo.current_project.facts) == 0

    def test_cascade_deletes_deductions_referencing_timeslot(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.remove_time_slot(ts.id)
        assert len(repo.current_project.deductions) == 0

    def test_cascade_deletes_rejections_referencing_timeslot(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        repo.remove_time_slot(ts.id)
        assert len(repo.current_project.rejections) == 0

    def test_cascade_preserves_unrelated_records(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts1 = repo.add_time_slot("09:00")
        ts2 = repo.add_time_slot("10:00")
        repo.add_fact(char.id, loc.id, ts1.id)
        repo.add_fact(char.id, loc.id, ts2.id)
        repo.remove_time_slot(ts1.id)
        assert len(repo.current_project.facts) == 1
        assert repo.current_project.facts[0].time_slot == ts2.id

    def test_cascade_deletes_accepted_deductions_for_timeslot(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.accept_deduction(ded.id)
        repo.remove_time_slot(ts.id)
        assert len(repo.current_project.deductions) == 0
        assert len(repo.current_project.facts) == 0


# ===========================================================================
# VAL-CASCADE-005: Delete Script cleans source_script_ids and supporting_script_ids
# ===========================================================================


class TestCascadeDeleteScript:
    """Removing a script removes its ID from every Fact.source_script_ids
    and every Deduction.supporting_script_ids. The facts and deductions
    themselves are NOT deleted."""

    def test_removes_from_fact_source_script_ids(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        script = repo.add_script("Some text", title="Scene 1")
        repo.add_fact(char.id, loc.id, ts.id, source_script_ids=[script.id])
        repo.remove_script(script.id)
        assert script.id not in repo.current_project.facts[0].source_script_ids

    def test_fact_not_deleted_when_script_removed(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        script = repo.add_script("Some text")
        repo.add_fact(char.id, loc.id, ts.id, source_script_ids=[script.id])
        repo.remove_script(script.id)
        assert len(repo.current_project.facts) == 1

    def test_removes_from_deduction_supporting_script_ids(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        script = repo.add_script("Some text")
        ded = _make_deduction(char.id, loc.id, ts.id, supporting_script_ids=[script.id])
        repo.add_deduction(ded)
        repo.remove_script(script.id)
        assert script.id not in repo.current_project.deductions[0].supporting_script_ids

    def test_deduction_not_deleted_when_script_removed(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        script = repo.add_script("Some text")
        ded = _make_deduction(char.id, loc.id, ts.id, supporting_script_ids=[script.id])
        repo.add_deduction(ded)
        repo.remove_script(script.id)
        assert len(repo.current_project.deductions) == 1

    def test_preserves_other_script_ids_in_fact(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        s1 = repo.add_script("Text 1")
        s2 = repo.add_script("Text 2")
        repo.add_fact(char.id, loc.id, ts.id, source_script_ids=[s1.id, s2.id])
        repo.remove_script(s1.id)
        assert s1.id not in repo.current_project.facts[0].source_script_ids
        assert s2.id in repo.current_project.facts[0].source_script_ids

    def test_preserves_other_script_ids_in_deduction(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        s1 = repo.add_script("Text 1")
        s2 = repo.add_script("Text 2")
        ded = _make_deduction(char.id, loc.id, ts.id, supporting_script_ids=[s1.id, s2.id])
        repo.add_deduction(ded)
        repo.remove_script(s1.id)
        assert s1.id not in repo.current_project.deductions[0].supporting_script_ids
        assert s2.id in repo.current_project.deductions[0].supporting_script_ids

    def test_script_with_no_references_deletes_cleanly(self, repo: JsonRepository) -> None:
        script = repo.add_script("Standalone text")
        assert repo.remove_script(script.id) is True
        assert len(repo.current_project.scripts) == 0


# ===========================================================================
# VAL-CASCADE-006: Cascade updates all three dedup indexes
# ===========================================================================


class TestCascadeUpdatesIndexes:
    """After cascading a character/location/time slot delete, _fact_index,
    _pending_index, and _rejection_index contain no triples involving
    the deleted entity's ID."""

    def test_fact_index_cleaned_after_character_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo._cache.fact_index
        repo.remove_character(char.id)
        assert triple not in repo._cache.fact_index

    def test_pending_index_cleaned_after_character_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo._cache.pending_index
        repo.remove_character(char.id)
        assert triple not in repo._cache.pending_index

    def test_rejection_index_cleaned_after_character_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        assert triple in repo._cache.rejection_index
        repo.remove_character(char.id)
        assert triple not in repo._cache.rejection_index

    def test_fact_index_cleaned_after_location_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        triple = (char.id, loc.id, ts.id)
        repo.remove_location(loc.id)
        assert triple not in repo._cache.fact_index

    def test_pending_index_cleaned_after_location_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        triple = (char.id, loc.id, ts.id)
        repo.remove_location(loc.id)
        assert triple not in repo._cache.pending_index

    def test_rejection_index_cleaned_after_location_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        repo.remove_location(loc.id)
        assert triple not in repo._cache.rejection_index

    def test_fact_index_cleaned_after_timeslot_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        triple = (char.id, loc.id, ts.id)
        repo.remove_time_slot(ts.id)
        assert triple not in repo._cache.fact_index

    def test_pending_index_cleaned_after_timeslot_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        triple = (char.id, loc.id, ts.id)
        repo.remove_time_slot(ts.id)
        assert triple not in repo._cache.pending_index

    def test_rejection_index_cleaned_after_timeslot_cascade(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        triple = (char.id, loc.id, ts.id)
        repo.remove_time_slot(ts.id)
        assert triple not in repo._cache.rejection_index

    def test_multiple_triples_cleaned_for_same_character(self, repo: JsonRepository) -> None:
        """Multiple facts/deductions for the same character all get cleaned."""
        char = repo.add_character("Alice")
        loc1 = repo.add_location("Library")
        loc2 = repo.add_location("Garden")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc1.id, ts.id)
        ded = _make_deduction(char.id, loc2.id, ts.id)
        repo.add_deduction(ded)
        repo.remove_character(char.id)
        assert (char.id, loc1.id, ts.id) not in repo._cache.fact_index
        assert (char.id, loc2.id, ts.id) not in repo._cache.pending_index

    def test_rejection_map_cleaned_after_cascade(self, repo: JsonRepository) -> None:
        """rejection_map should also be cleaned when rejections are cascaded."""
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        assert ded.id in repo._cache.rejection_map
        repo.remove_character(char.id)
        assert ded.id not in repo._cache.rejection_map


# ===========================================================================
# VAL-CASCADE-007: Cascade delete is atomic with persistence
# ===========================================================================


class TestCascadeAtomicPersistence:
    """After a cascading delete, save() is called once. Reloading the project
    from disk shows the fully cascaded state with no orphaned references."""

    def test_character_cascade_persists(self, repo: JsonRepository, tmp_path: Path) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        _make_deduction(char.id, loc.id, ts.id + "_other")
        # Add a deduction with a different triple to make it unique
        char2_loc = repo.add_location("Kitchen")
        ts2 = repo.add_time_slot("10:00")
        ded2 = _make_deduction(char.id, char2_loc.id, ts2.id)
        repo.add_deduction(ded2)
        repo.remove_character(char.id)
        # Reload from disk
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert len(repo2.current_project.characters) == 0
        assert len(repo2.current_project.facts) == 0
        assert len(repo2.current_project.deductions) == 0

    def test_location_cascade_persists(self, repo: JsonRepository, tmp_path: Path) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        repo.remove_location(loc.id)
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert len(repo2.current_project.locations) == 0
        assert len(repo2.current_project.facts) == 0

    def test_timeslot_cascade_persists(self, repo: JsonRepository, tmp_path: Path) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, loc.id, ts.id)
        repo.remove_time_slot(ts.id)
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert len(repo2.current_project.time_slots) == 0
        assert len(repo2.current_project.facts) == 0

    def test_timeslot_cascade_persists_deductions_and_rejections(
        self, repo: JsonRepository, tmp_path: Path
    ) -> None:
        """Removing a time slot cascades facts, deductions, AND rejections;
        all three are gone from disk after reload."""
        char = repo.add_character("Alice")
        loc1 = repo.add_location("Library")
        loc2 = repo.add_location("Garden")
        loc3 = repo.add_location("Kitchen")
        ts = repo.add_time_slot("09:00")
        # Create a fact referencing the time slot
        repo.add_fact(char.id, loc1.id, ts.id)
        # Create a pending deduction referencing the time slot
        ded_pending = _make_deduction(char.id, loc2.id, ts.id)
        repo.add_deduction(ded_pending)
        # Create a rejected deduction+rejection referencing the time slot
        ded_reject = _make_deduction(char.id, loc3.id, ts.id)
        repo.add_deduction(ded_reject)
        repo.reject_deduction(ded_reject.id)

        # Verify records exist before removal
        assert len(repo.current_project.facts) == 1
        assert len(repo.current_project.deductions) == 2
        assert len(repo.current_project.rejections) == 1

        # Remove the time slot (cascades all dependent records)
        repo.remove_time_slot(ts.id)

        # Verify in-memory state
        assert len(repo.current_project.facts) == 0
        assert len(repo.current_project.deductions) == 0
        assert len(repo.current_project.rejections) == 0

        # Reload from disk and verify persistence
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert len(repo2.current_project.time_slots) == 0
        assert len(repo2.current_project.facts) == 0
        assert len(repo2.current_project.deductions) == 0
        assert len(repo2.current_project.rejections) == 0

    def test_script_cascade_persists(self, repo: JsonRepository, tmp_path: Path) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        script = repo.add_script("Text")
        repo.add_fact(char.id, loc.id, ts.id, source_script_ids=[script.id])
        repo.remove_script(script.id)
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        # Fact preserved but source_script_ids cleaned
        assert len(repo2.current_project.facts) == 1
        assert script.id not in repo2.current_project.facts[0].source_script_ids

    def test_character_cascade_cleans_script_metadata_on_disk(
        self, repo: JsonRepository, tmp_path: Path
    ) -> None:
        char = repo.add_character("Alice")
        script = repo.add_script("Scene text")
        script.metadata.characters_mentioned = ["Alice", "Bob"]
        repo.save()
        repo.remove_character(char.id)
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert "Alice" not in repo2.current_project.scripts[0].metadata.characters_mentioned
        assert "Bob" in repo2.current_project.scripts[0].metadata.characters_mentioned

    def test_cascade_with_rejections_persists(self, repo: JsonRepository, tmp_path: Path) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        ded = _make_deduction(char.id, loc.id, ts.id)
        repo.add_deduction(ded)
        repo.reject_deduction(ded.id)
        repo.remove_character(char.id)
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        assert len(repo2.current_project.rejections) == 0
        assert len(repo2.current_project.deductions) == 0

    def test_reload_indexes_correct_after_cascade(
        self, repo: JsonRepository, tmp_path: Path
    ) -> None:
        """Reloaded indexes should be fully consistent after cascade."""
        alice = repo.add_character("Alice")
        bob = repo.add_character("Bob")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(alice.id, loc.id, ts.id)
        repo.add_fact(bob.id, loc.id, ts.id)
        repo.remove_character(alice.id)
        proj_id = repo.current_project.id
        repo2 = JsonRepository(store=JsonStore(data_dir=tmp_path))
        repo2.load_project(proj_id)
        # Only Bob's fact triple should be in the index
        assert (alice.id, loc.id, ts.id) not in repo2._cache.fact_index
        assert (bob.id, loc.id, ts.id) in repo2._cache.fact_index
        # Only Bob should be in char_by_id
        assert alice.id not in repo2._cache.char_by_id
        assert bob.id in repo2._cache.char_by_id


# ===========================================================================
# VAL-CASCADE-008: Clean delete (entity with no references) succeeds
# ===========================================================================


class TestCleanDeleteNoReferences:
    """Deleting an entity that has zero referencing facts/deductions/rejections
    succeeds, reduces entity count by 1, and does not modify any other
    collections."""

    def test_character_with_no_references_deletes_cleanly(self, repo: JsonRepository) -> None:
        alice = repo.add_character("Alice")
        bob = repo.add_character("Bob")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(bob.id, loc.id, ts.id)
        initial_fact_count = len(repo.current_project.facts)
        initial_loc_count = len(repo.current_project.locations)
        repo.remove_character(alice.id)
        # Alice removed, everything else unchanged
        assert len(repo.current_project.characters) == 1
        assert repo.current_project.characters[0].id == bob.id
        assert len(repo.current_project.facts) == initial_fact_count
        assert len(repo.current_project.locations) == initial_loc_count

    def test_location_with_no_references_deletes_cleanly(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        lib = repo.add_location("Library")
        garden = repo.add_location("Garden")
        ts = repo.add_time_slot("09:00")
        repo.add_fact(char.id, lib.id, ts.id)
        initial_fact_count = len(repo.current_project.facts)
        repo.remove_location(garden.id)
        assert len(repo.current_project.locations) == 1
        assert len(repo.current_project.facts) == initial_fact_count

    def test_timeslot_with_no_references_deletes_cleanly(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts1 = repo.add_time_slot("09:00")
        ts2 = repo.add_time_slot("10:00")
        repo.add_fact(char.id, loc.id, ts1.id)
        initial_fact_count = len(repo.current_project.facts)
        repo.remove_time_slot(ts2.id)
        assert len(repo.current_project.time_slots) == 1
        assert len(repo.current_project.facts) == initial_fact_count

    def test_script_with_no_references_deletes_cleanly(self, repo: JsonRepository) -> None:
        char = repo.add_character("Alice")
        loc = repo.add_location("Library")
        ts = repo.add_time_slot("09:00")
        script = repo.add_script("Standalone")
        repo.add_fact(char.id, loc.id, ts.id)
        initial_fact_count = len(repo.current_project.facts)
        initial_char_count = len(repo.current_project.characters)
        repo.remove_script(script.id)
        assert len(repo.current_project.scripts) == 0
        assert len(repo.current_project.facts) == initial_fact_count
        assert len(repo.current_project.characters) == initial_char_count

    def test_lone_entity_deletes_cleanly(self, repo: JsonRepository) -> None:
        """An entity in a project with nothing else should delete without error."""
        char = repo.add_character("Alice")
        repo.remove_character(char.id)
        assert len(repo.current_project.characters) == 0
        assert len(repo.current_project.facts) == 0
        assert len(repo.current_project.deductions) == 0
        assert len(repo.current_project.rejections) == 0
