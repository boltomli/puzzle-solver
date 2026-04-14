"""Tests for CacheManager (TDD - Red Phase first, then implementation).

Covers all index types, invalidation, rebuild correctness,
rapid sequential mutations, and edge cases.
"""

from __future__ import annotations

from src.models.puzzle import (
    Character,
    Deduction,
    DeductionStatus,
    Fact,
    Location,
    Project,
    Rejection,
    SourceType,
    TimeSlot,
)
from src.storage.cache_manager import CacheManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_project(**kwargs) -> Project:
    """Create a minimal project for testing."""
    return Project(name=kwargs.get("name", "Test Project"))


def add_char(proj: Project, name: str) -> Character:
    char = Character(name=name)
    proj.characters.append(char)
    return char


def add_loc(proj: Project, name: str) -> Location:
    loc = Location(name=name)
    proj.locations.append(loc)
    return loc


def add_ts(proj: Project, label: str, description: str = "") -> TimeSlot:
    ts = TimeSlot(label=label, description=description, sort_order=len(proj.time_slots))
    proj.time_slots.append(ts)
    return ts


def add_fact(proj: Project, char: Character, loc: Location, ts: TimeSlot) -> Fact:
    fact = Fact(
        character_id=char.id,
        location_id=loc.id,
        time_slot=ts.id,
        source_type=SourceType.user_input,
    )
    proj.facts.append(fact)
    return fact


def add_deduction(
    proj: Project,
    char: Character,
    loc: Location,
    ts: TimeSlot,
    status: DeductionStatus = DeductionStatus.pending,
) -> Deduction:
    from src.models.puzzle import ConfidenceLevel

    ded = Deduction(
        character_id=char.id,
        location_id=loc.id,
        time_slot=ts.id,
        confidence=ConfidenceLevel.medium,
        reasoning="test reasoning",
        status=status,
    )
    proj.deductions.append(ded)
    return ded


def add_rejection(
    proj: Project,
    char: Character,
    loc: Location,
    ts: TimeSlot,
    reason: str = "rejected",
    from_deduction_id: str | None = None,
) -> Rejection:
    rej = Rejection(
        character_id=char.id,
        location_id=loc.id,
        time_slot=ts.id,
        reason=reason,
        from_deduction_id=from_deduction_id,
    )
    proj.rejections.append(rej)
    return rej


# ---------------------------------------------------------------------------
# Tests: CacheManager initialization
# ---------------------------------------------------------------------------


class TestCacheManagerInit:
    def test_empty_on_init(self):
        """CacheManager starts with empty indexes."""
        cm = CacheManager()
        assert cm.char_by_id == {}
        assert cm.loc_by_id == {}
        assert cm.ts_by_id == {}
        assert cm.char_by_name == {}
        assert cm.loc_by_name == {}
        assert cm.ts_label_map == {}
        assert cm.rejection_map == {}
        assert cm.fact_index == set()
        assert cm.pending_index == set()
        assert cm.rejection_index == set()


# ---------------------------------------------------------------------------
# Tests: rebuild() - entity-by-id indexes
# ---------------------------------------------------------------------------


class TestRebuildEntityById:
    def test_char_by_id_populated(self):
        """rebuild() builds char_by_id index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.char_by_id[char.id] is char

    def test_loc_by_id_populated(self):
        """rebuild() builds loc_by_id index."""
        proj = make_project()
        loc = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.loc_by_id[loc.id] is loc

    def test_ts_by_id_populated(self):
        """rebuild() builds ts_by_id index."""
        proj = make_project()
        ts = add_ts(proj, "16:00", "第一天")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.ts_by_id[ts.id] is ts

    def test_unknown_char_id_returns_none(self):
        """char_by_id returns None for unknown IDs."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.char_by_id.get("nonexistent") is None

    def test_unknown_loc_id_returns_none(self):
        """loc_by_id returns None for unknown IDs."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.loc_by_id.get("nonexistent") is None

    def test_unknown_ts_id_returns_none(self):
        """ts_by_id returns None for unknown IDs."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.ts_by_id.get("nonexistent") is None

    def test_multiple_chars_all_indexed(self):
        """All characters are indexed by ID."""
        proj = make_project()
        chars = [add_char(proj, f"Char{i}") for i in range(5)]
        cm = CacheManager()
        cm.rebuild(proj)
        for char in chars:
            assert cm.char_by_id[char.id] is char

    def test_multiple_locs_all_indexed(self):
        """All locations are indexed by ID."""
        proj = make_project()
        locs = [add_loc(proj, f"Loc{i}") for i in range(5)]
        cm = CacheManager()
        cm.rebuild(proj)
        for loc in locs:
            assert cm.loc_by_id[loc.id] is loc

    def test_multiple_ts_all_indexed(self):
        """All time slots are indexed by ID."""
        proj = make_project()
        slots = [add_ts(proj, f"1{i}:00") for i in range(5)]
        cm = CacheManager()
        cm.rebuild(proj)
        for ts in slots:
            assert cm.ts_by_id[ts.id] is ts


# ---------------------------------------------------------------------------
# Tests: rebuild() - case-insensitive by-name indexes
# ---------------------------------------------------------------------------


class TestRebuildByName:
    def test_char_by_name_lowercase_key(self):
        """char_by_name uses lowercase keys."""
        proj = make_project()
        char = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.char_by_name["alice"] is char
        assert "Alice" not in cm.char_by_name

    def test_loc_by_name_lowercase_key(self):
        """loc_by_name uses lowercase keys."""
        proj = make_project()
        loc = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.loc_by_name["library"] is loc
        assert "Library" not in cm.loc_by_name

    def test_char_by_name_last_writer_wins(self):
        """char_by_name last-writer-wins for duplicate names (same lowercased key)."""
        proj = make_project()
        add_char(proj, "Alice")
        char2 = add_char(proj, "alice")  # same lowercase key
        cm = CacheManager()
        cm.rebuild(proj)
        # Last writer wins means char2 is in the index
        assert cm.char_by_name["alice"] is char2

    def test_loc_by_name_last_writer_wins(self):
        """loc_by_name last-writer-wins for duplicate names."""
        proj = make_project()
        add_loc(proj, "Library")
        loc2 = add_loc(proj, "LIBRARY")  # same lowercase key
        cm = CacheManager()
        cm.rebuild(proj)
        # Last writer wins
        assert cm.loc_by_name["library"] is loc2

    def test_char_by_name_mixed_case(self):
        """char_by_name accessible via any case."""
        proj = make_project()
        char = add_char(proj, "Bob Smith")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.char_by_name["bob smith"] is char


# ---------------------------------------------------------------------------
# Tests: rebuild() - ts_label_map
# ---------------------------------------------------------------------------


class TestRebuildTsLabelMap:
    def test_ts_label_map_with_description(self):
        """ts_label_map includes 'HH:MM(desc)' key."""
        proj = make_project()
        ts = add_ts(proj, "16:00", "第一天")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.ts_label_map["16:00(第一天)"] == ts.id

    def test_ts_label_map_bare_label(self):
        """ts_label_map also includes bare 'HH:MM' key."""
        proj = make_project()
        ts = add_ts(proj, "16:00", "第一天")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.ts_label_map["16:00"] == ts.id

    def test_ts_label_map_no_description(self):
        """ts_label_map for ts with no description uses bare label."""
        proj = make_project()
        ts = add_ts(proj, "08:00")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.ts_label_map["08:00"] == ts.id
        # No key with empty desc
        assert "08:00()" not in cm.ts_label_map

    def test_ts_label_map_bare_label_first_writer_wins(self):
        """For bare label conflicts, first-writer-wins."""
        proj = make_project()
        ts1 = add_ts(proj, "16:00", "第一天")  # adds "16:00(第一天)" and bare "16:00"
        ts2 = add_ts(proj, "16:00", "第二天")  # adds "16:00(第二天)" but bare "16:00" already set
        cm = CacheManager()
        cm.rebuild(proj)
        # Full keys both present
        assert cm.ts_label_map["16:00(第一天)"] == ts1.id
        assert cm.ts_label_map["16:00(第二天)"] == ts2.id
        # Bare label: first-writer-wins (ts1)
        assert cm.ts_label_map["16:00"] == ts1.id

    def test_ts_label_map_multiple_slots(self):
        """ts_label_map works for multiple distinct time slots."""
        proj = make_project()
        ts1 = add_ts(proj, "08:00")
        ts2 = add_ts(proj, "12:00", "Lunch")
        ts3 = add_ts(proj, "18:00", "Evening")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.ts_label_map["08:00"] == ts1.id
        assert cm.ts_label_map["12:00(Lunch)"] == ts2.id
        assert cm.ts_label_map["12:00"] == ts2.id
        assert cm.ts_label_map["18:00(Evening)"] == ts3.id
        assert cm.ts_label_map["18:00"] == ts3.id


# ---------------------------------------------------------------------------
# Tests: rebuild() - rejection_map
# ---------------------------------------------------------------------------


class TestRebuildRejectionMap:
    def test_rejection_map_with_from_deduction_id(self):
        """rejection_map maps from_deduction_id to reason."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        ded = add_deduction(proj, char, loc, ts, DeductionStatus.rejected)
        add_rejection(proj, char, loc, ts, reason="Wrong place", from_deduction_id=ded.id)
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.rejection_map[ded.id] == "Wrong place"

    def test_rejection_map_excludes_none_keys(self):
        """rejection_map excludes rejections where from_deduction_id is None."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        add_rejection(proj, char, loc, ts, reason="User rejection", from_deduction_id=None)
        cm = CacheManager()
        cm.rebuild(proj)
        # None key not in map
        assert None not in cm.rejection_map
        assert len(cm.rejection_map) == 0

    def test_rejection_map_multiple_entries(self):
        """rejection_map handles multiple entries."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts1 = add_ts(proj, "16:00")
        ts2 = add_ts(proj, "17:00")
        ded1 = add_deduction(proj, char, loc, ts1, DeductionStatus.rejected)
        ded2 = add_deduction(proj, char, loc, ts2, DeductionStatus.rejected)
        add_rejection(proj, char, loc, ts1, reason="Reason 1", from_deduction_id=ded1.id)
        add_rejection(proj, char, loc, ts2, reason="Reason 2", from_deduction_id=ded2.id)
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.rejection_map[ded1.id] == "Reason 1"
        assert cm.rejection_map[ded2.id] == "Reason 2"

    def test_rejection_map_mixed_none_and_valid(self):
        """rejection_map filters None keys but keeps valid from_deduction_id entries."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts1 = add_ts(proj, "16:00")
        ts2 = add_ts(proj, "17:00")
        ded = add_deduction(proj, char, loc, ts1, DeductionStatus.rejected)
        add_rejection(proj, char, loc, ts1, reason="Valid", from_deduction_id=ded.id)
        add_rejection(proj, char, loc, ts2, reason="No deduction", from_deduction_id=None)
        cm = CacheManager()
        cm.rebuild(proj)
        assert len(cm.rejection_map) == 1
        assert cm.rejection_map[ded.id] == "Valid"


# ---------------------------------------------------------------------------
# Tests: rebuild() - triple dedup indexes
# ---------------------------------------------------------------------------


class TestRebuildTripleIndexes:
    def test_fact_index_populated(self):
        """rebuild() populates fact_index with (char_id, loc_id, ts_id) tuples."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        add_fact(proj, char, loc, ts)
        cm = CacheManager()
        cm.rebuild(proj)
        assert (char.id, loc.id, ts.id) in cm.fact_index

    def test_pending_index_only_pending_deductions(self):
        """rebuild() pending_index only includes pending deductions."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts1 = add_ts(proj, "16:00")
        ts2 = add_ts(proj, "17:00")
        ts3 = add_ts(proj, "18:00")
        add_deduction(proj, char, loc, ts1, DeductionStatus.pending)
        add_deduction(proj, char, loc, ts2, DeductionStatus.accepted)
        add_deduction(proj, char, loc, ts3, DeductionStatus.rejected)
        cm = CacheManager()
        cm.rebuild(proj)
        assert (char.id, loc.id, ts1.id) in cm.pending_index
        assert (char.id, loc.id, ts2.id) not in cm.pending_index
        assert (char.id, loc.id, ts3.id) not in cm.pending_index

    def test_rejection_index_populated(self):
        """rebuild() rejection_index has (char_id, loc_id, ts_id) from all rejections."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        add_rejection(proj, char, loc, ts, reason="test")
        cm = CacheManager()
        cm.rebuild(proj)
        assert (char.id, loc.id, ts.id) in cm.rejection_index

    def test_indexes_empty_for_no_data(self):
        """Empty project results in empty triple indexes."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.fact_index == set()
        assert cm.pending_index == set()
        assert cm.rejection_index == set()

    def test_multiple_facts_all_indexed(self):
        """Multiple facts all appear in fact_index."""
        proj = make_project()
        char1 = add_char(proj, "Alice")
        char2 = add_char(proj, "Bob")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        add_fact(proj, char1, loc, ts)
        add_fact(proj, char2, loc, ts)
        cm = CacheManager()
        cm.rebuild(proj)
        assert (char1.id, loc.id, ts.id) in cm.fact_index
        assert (char2.id, loc.id, ts.id) in cm.fact_index


# ---------------------------------------------------------------------------
# Tests: rebuild() - empty project edge case
# ---------------------------------------------------------------------------


class TestRebuildEmptyProject:
    def test_empty_project_all_indexes_empty(self):
        """rebuild() on empty project leaves all indexes empty."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.char_by_id == {}
        assert cm.loc_by_id == {}
        assert cm.ts_by_id == {}
        assert cm.char_by_name == {}
        assert cm.loc_by_name == {}
        assert cm.ts_label_map == {}
        assert cm.rejection_map == {}
        assert cm.fact_index == set()
        assert cm.pending_index == set()
        assert cm.rejection_index == set()

    def test_rebuild_replaces_previous_state(self):
        """rebuild() replaces previous index contents (not additive)."""
        proj1 = make_project()
        char1 = add_char(proj1, "Alice")
        cm = CacheManager()
        cm.rebuild(proj1)
        assert char1.id in cm.char_by_id

        # Rebuild with different project
        proj2 = make_project()
        char2 = add_char(proj2, "Bob")
        cm.rebuild(proj2)
        # Old char should be gone, new char present
        assert char1.id not in cm.char_by_id
        assert char2.id in cm.char_by_id


# ---------------------------------------------------------------------------
# Tests: invalidate_character
# ---------------------------------------------------------------------------


class TestInvalidateCharacter:
    def test_invalidate_add_character_updates_char_by_id(self):
        """invalidate_character('add', char) adds char to char_by_id."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        char = Character(name="Alice")
        cm.invalidate_character("add", char)
        assert cm.char_by_id[char.id] is char

    def test_invalidate_add_character_updates_char_by_name(self):
        """invalidate_character('add', char) adds char to char_by_name."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        char = Character(name="Alice")
        cm.invalidate_character("add", char)
        assert cm.char_by_name["alice"] is char

    def test_invalidate_remove_character_removes_from_char_by_id(self):
        """invalidate_character('remove', char) removes char from char_by_id."""
        proj = make_project()
        char = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        cm.invalidate_character("remove", char)
        assert char.id not in cm.char_by_id

    def test_invalidate_remove_character_removes_from_char_by_name(self):
        """invalidate_character('remove', char) removes char from char_by_name."""
        proj = make_project()
        char = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        cm.invalidate_character("remove", char)
        assert "alice" not in cm.char_by_name

    def test_invalidate_update_character_updates_both_indexes(self):
        """invalidate_character('update', char, old_name=X) updates indexes."""
        proj = make_project()
        char = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        # Rename
        char.name = "Alicia"
        cm.invalidate_character("update", char, old_name="Alice")
        # Old name gone, new name present
        assert "alice" not in cm.char_by_name
        assert "alicia" in cm.char_by_name
        assert cm.char_by_name["alicia"] is char

    def test_invalidate_remove_unknown_char_does_not_raise(self):
        """Removing an unknown char doesn't raise."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        char = Character(name="Ghost")
        cm.invalidate_character("remove", char)  # Should not raise


# ---------------------------------------------------------------------------
# Tests: invalidate_location
# ---------------------------------------------------------------------------


class TestInvalidateLocation:
    def test_invalidate_add_location(self):
        """invalidate_location('add', loc) adds to both indexes."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        loc = Location(name="Dungeon")
        cm.invalidate_location("add", loc)
        assert cm.loc_by_id[loc.id] is loc
        assert cm.loc_by_name["dungeon"] is loc

    def test_invalidate_remove_location(self):
        """invalidate_location('remove', loc) removes from both indexes."""
        proj = make_project()
        loc = add_loc(proj, "Dungeon")
        cm = CacheManager()
        cm.rebuild(proj)
        cm.invalidate_location("remove", loc)
        assert loc.id not in cm.loc_by_id
        assert "dungeon" not in cm.loc_by_name

    def test_invalidate_update_location(self):
        """invalidate_location('update', loc, old_name=X) updates indexes."""
        proj = make_project()
        loc = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)
        loc.name = "Archive"
        cm.invalidate_location("update", loc, old_name="Library")
        assert "library" not in cm.loc_by_name
        assert "archive" in cm.loc_by_name
        assert cm.loc_by_name["archive"] is loc


# ---------------------------------------------------------------------------
# Tests: invalidate_time_slot
# ---------------------------------------------------------------------------


class TestInvalidateTimeSlot:
    def test_invalidate_add_time_slot(self):
        """invalidate_time_slot('add', ts) adds to ts_by_id and ts_label_map."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        ts = TimeSlot(label="20:00", description="Night")
        cm.invalidate_time_slot("add", ts)
        assert cm.ts_by_id[ts.id] is ts
        assert cm.ts_label_map["20:00(Night)"] == ts.id
        assert cm.ts_label_map.get("20:00") == ts.id  # bare label also added

    def test_invalidate_add_time_slot_no_description(self):
        """invalidate_time_slot('add', ts) with no description only adds bare label."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        ts = TimeSlot(label="09:00")
        cm.invalidate_time_slot("add", ts)
        assert cm.ts_label_map["09:00"] == ts.id

    def test_invalidate_remove_time_slot(self):
        """invalidate_time_slot('remove', ts) cleans ts_by_id and ts_label_map."""
        proj = make_project()
        ts = add_ts(proj, "16:00", "Evening")
        cm = CacheManager()
        cm.rebuild(proj)
        cm.invalidate_time_slot("remove", ts)
        assert ts.id not in cm.ts_by_id
        assert "16:00(Evening)" not in cm.ts_label_map
        # Bare label also removed (since no other ts with same bare label)
        assert "16:00" not in cm.ts_label_map

    def test_invalidate_add_bare_label_first_writer_wins(self):
        """When adding ts with bare label that already exists, first-writer-wins."""
        proj = make_project()
        ts1 = add_ts(proj, "16:00", "First")
        cm = CacheManager()
        cm.rebuild(proj)
        # ts1 owns the bare "16:00" label
        assert cm.ts_label_map["16:00"] == ts1.id
        # Add ts2 with same bare label
        ts2 = TimeSlot(label="16:00", description="Second")
        cm.invalidate_time_slot("add", ts2)
        # bare label should still point to ts1 (first-writer-wins)
        assert cm.ts_label_map["16:00"] == ts1.id
        # Full key for ts2 is added
        assert cm.ts_label_map["16:00(Second)"] == ts2.id


# ---------------------------------------------------------------------------
# Tests: invalidate_fact
# ---------------------------------------------------------------------------


class TestInvalidateFact:
    def test_invalidate_add_fact(self):
        """invalidate_fact('add', fact) adds triple to fact_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        cm = CacheManager()
        cm.rebuild(proj)
        fact = Fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            source_type=SourceType.user_input,
        )
        cm.invalidate_fact("add", fact)
        assert (char.id, loc.id, ts.id) in cm.fact_index

    def test_invalidate_remove_fact(self):
        """invalidate_fact('remove', fact) removes triple from fact_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        fact = add_fact(proj, char, loc, ts)
        cm = CacheManager()
        cm.rebuild(proj)
        cm.invalidate_fact("remove", fact)
        assert (char.id, loc.id, ts.id) not in cm.fact_index


# ---------------------------------------------------------------------------
# Tests: invalidate_deduction
# ---------------------------------------------------------------------------


class TestInvalidateDeduction:
    def test_invalidate_add_pending_deduction(self):
        """invalidate_deduction('add', ded) adds triple to pending_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        cm = CacheManager()
        cm.rebuild(proj)
        ded = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence="medium",
            reasoning="test",
            status=DeductionStatus.pending,
        )
        cm.invalidate_deduction("add", ded)
        assert (char.id, loc.id, ts.id) in cm.pending_index

    def test_invalidate_accept_deduction(self):
        """invalidate_deduction('accept', ded, fact=fact) removes from pending, adds to fact_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        ded = add_deduction(proj, char, loc, ts, DeductionStatus.pending)
        cm = CacheManager()
        cm.rebuild(proj)
        assert (char.id, loc.id, ts.id) in cm.pending_index

        fact = Fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            source_type=SourceType.ai_deduction,
            from_deduction_id=ded.id,
        )
        cm.invalidate_deduction("accept", ded, fact=fact)
        assert (char.id, loc.id, ts.id) not in cm.pending_index
        assert (char.id, loc.id, ts.id) in cm.fact_index

    def test_invalidate_reject_deduction(self):
        """invalidate_deduction('reject', ded, rejection=rej) removes from pending, adds to rejection_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        ded = add_deduction(proj, char, loc, ts, DeductionStatus.pending)
        cm = CacheManager()
        cm.rebuild(proj)
        rej = Rejection(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            reason="Wrong",
            from_deduction_id=ded.id,
        )
        cm.invalidate_deduction("reject", ded, rejection=rej)
        assert (char.id, loc.id, ts.id) not in cm.pending_index
        assert (char.id, loc.id, ts.id) in cm.rejection_index

    def test_invalidate_reject_deduction_updates_rejection_map(self):
        """invalidate_deduction('reject', ded, rejection=rej) updates rejection_map."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        ded = add_deduction(proj, char, loc, ts, DeductionStatus.pending)
        cm = CacheManager()
        cm.rebuild(proj)
        rej = Rejection(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            reason="Wrong location",
            from_deduction_id=ded.id,
        )
        cm.invalidate_deduction("reject", ded, rejection=rej)
        assert cm.rejection_map[ded.id] == "Wrong location"

    def test_invalidate_clear_pending_deductions(self):
        """invalidate_deduction('clear_pending', ...) clears pending_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        add_deduction(proj, char, loc, ts, DeductionStatus.pending)
        cm = CacheManager()
        cm.rebuild(proj)
        assert len(cm.pending_index) > 0
        cm.invalidate_deduction("clear_pending", None)
        assert cm.pending_index == set()


# ---------------------------------------------------------------------------
# Tests: invalidate_rejection
# ---------------------------------------------------------------------------


class TestInvalidateRejection:
    def test_invalidate_add_rejection(self):
        """invalidate_rejection('add', rej) adds triple to rejection_index and updates rejection_map."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        ded = add_deduction(proj, char, loc, ts, DeductionStatus.rejected)
        cm = CacheManager()
        cm.rebuild(proj)
        rej = Rejection(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            reason="Nope",
            from_deduction_id=ded.id,
        )
        cm.invalidate_rejection("add", rej)
        assert (char.id, loc.id, ts.id) in cm.rejection_index
        assert cm.rejection_map[ded.id] == "Nope"

    def test_invalidate_add_rejection_none_from_deduction_id(self):
        """invalidate_rejection('add', rej) with None from_deduction_id doesn't add to rejection_map."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        cm = CacheManager()
        cm.rebuild(proj)
        rej = Rejection(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            reason="User rejection",
            from_deduction_id=None,
        )
        cm.invalidate_rejection("add", rej)
        assert (char.id, loc.id, ts.id) in cm.rejection_index
        assert None not in cm.rejection_map


# ---------------------------------------------------------------------------
# Tests: consistency after add/remove/update sequences
# ---------------------------------------------------------------------------


class TestConsistencyAfterMutations:
    def test_add_then_remove_character_clean(self):
        """Adding then removing a character leaves indexes clean."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        char = Character(name="Temp")
        cm.invalidate_character("add", char)
        assert char.id in cm.char_by_id
        cm.invalidate_character("remove", char)
        assert char.id not in cm.char_by_id
        assert "temp" not in cm.char_by_name

    def test_add_then_remove_location_clean(self):
        """Adding then removing a location leaves indexes clean."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        loc = Location(name="Barn")
        cm.invalidate_location("add", loc)
        assert loc.id in cm.loc_by_id
        cm.invalidate_location("remove", loc)
        assert loc.id not in cm.loc_by_id
        assert "barn" not in cm.loc_by_name

    def test_add_then_remove_time_slot_clean(self):
        """Adding then removing a time slot leaves indexes clean."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)
        ts = TimeSlot(label="22:00", description="Midnight")
        cm.invalidate_time_slot("add", ts)
        assert ts.id in cm.ts_by_id
        cm.invalidate_time_slot("remove", ts)
        assert ts.id not in cm.ts_by_id
        assert "22:00(Midnight)" not in cm.ts_label_map
        assert "22:00" not in cm.ts_label_map

    def test_accept_deduction_updates_all_indexes(self):
        """Accepting a deduction moves triple from pending to fact_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        ded = add_deduction(proj, char, loc, ts, DeductionStatus.pending)
        cm = CacheManager()
        cm.rebuild(proj)
        assert (char.id, loc.id, ts.id) in cm.pending_index
        assert (char.id, loc.id, ts.id) not in cm.fact_index
        fact = Fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            source_type=SourceType.ai_deduction,
            from_deduction_id=ded.id,
        )
        cm.invalidate_deduction("accept", ded, fact=fact)
        assert (char.id, loc.id, ts.id) not in cm.pending_index
        assert (char.id, loc.id, ts.id) in cm.fact_index

    def test_reject_deduction_updates_all_indexes(self):
        """Rejecting a deduction moves triple from pending to rejection_index."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        ded = add_deduction(proj, char, loc, ts, DeductionStatus.pending)
        cm = CacheManager()
        cm.rebuild(proj)
        rej = Rejection(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            reason="Wrong",
            from_deduction_id=ded.id,
        )
        cm.invalidate_deduction("reject", ded, rejection=rej)
        assert (char.id, loc.id, ts.id) not in cm.pending_index
        assert (char.id, loc.id, ts.id) in cm.rejection_index
        assert cm.rejection_map[ded.id] == "Wrong"


# ---------------------------------------------------------------------------
# Tests: rebuild() matches incremental invalidation
# ---------------------------------------------------------------------------


class TestRebuildMatchesIncremental:
    def test_rebuild_matches_incremental_after_adding_entities(self):
        """rebuild() from scratch matches state built via incremental invalidation."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00", "Evening")

        # Build via incremental
        cm_incremental = CacheManager()
        cm_incremental.invalidate_character("add", char)
        cm_incremental.invalidate_location("add", loc)
        cm_incremental.invalidate_time_slot("add", ts)

        # Build via rebuild
        cm_rebuild = CacheManager()
        cm_rebuild.rebuild(proj)

        assert cm_incremental.char_by_id == cm_rebuild.char_by_id
        assert cm_incremental.loc_by_id == cm_rebuild.loc_by_id
        assert cm_incremental.ts_by_id == cm_rebuild.ts_by_id
        assert cm_incremental.char_by_name == cm_rebuild.char_by_name
        assert cm_incremental.loc_by_name == cm_rebuild.loc_by_name
        assert cm_incremental.ts_label_map == cm_rebuild.ts_label_map

    def test_rebuild_matches_incremental_after_facts(self):
        """rebuild() fact_index matches incremental invalidation."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        fact = add_fact(proj, char, loc, ts)

        # Build via rebuild
        cm_rebuild = CacheManager()
        cm_rebuild.rebuild(proj)

        # Build via incremental
        cm_incr = CacheManager()
        cm_incr.invalidate_fact("add", fact)

        assert cm_rebuild.fact_index == cm_incr.fact_index


# ---------------------------------------------------------------------------
# Tests: rapid sequential mutations
# ---------------------------------------------------------------------------


class TestRapidSequentialMutations:
    def test_rapid_add_remove_characters_consistent(self):
        """Rapid add/remove leaves indexes consistent."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)

        chars = [Character(name=f"Char{i}") for i in range(10)]
        for char in chars:
            cm.invalidate_character("add", char)

        # Remove every other one
        for i in range(0, 10, 2):
            cm.invalidate_character("remove", chars[i])

        # Verify state
        for i in range(10):
            if i % 2 == 0:
                assert chars[i].id not in cm.char_by_id
                assert f"char{i}" not in cm.char_by_name
            else:
                assert chars[i].id in cm.char_by_id
                assert f"char{i}" in cm.char_by_name

    def test_rapid_add_remove_facts_consistent(self):
        """Rapid add/remove of facts leaves fact_index consistent."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        cm = CacheManager()
        cm.rebuild(proj)

        # Add and remove the same fact triple multiple times
        fact = Fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            source_type=SourceType.user_input,
        )
        for _ in range(5):
            cm.invalidate_fact("add", fact)
            assert (char.id, loc.id, ts.id) in cm.fact_index
            cm.invalidate_fact("remove", fact)
            assert (char.id, loc.id, ts.id) not in cm.fact_index

    def test_rapid_add_remove_locations_consistent(self):
        """Rapid location mutations stay consistent."""
        proj = make_project()
        cm = CacheManager()
        cm.rebuild(proj)

        locs = [Location(name=f"Loc{i}") for i in range(10)]
        for loc in locs:
            cm.invalidate_location("add", loc)
        for loc in locs:
            cm.invalidate_location("remove", loc)

        assert cm.loc_by_id == {}
        assert cm.loc_by_name == {}

    def test_rapid_deduction_lifecycle(self):
        """Add deduction, accept it, verify state is consistent."""
        proj = make_project()
        char = add_char(proj, "Alice")
        loc = add_loc(proj, "Library")
        ts = add_ts(proj, "16:00")
        cm = CacheManager()
        cm.rebuild(proj)

        ded = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence="medium",
            reasoning="test",
            status=DeductionStatus.pending,
        )
        cm.invalidate_deduction("add", ded)
        assert (char.id, loc.id, ts.id) in cm.pending_index

        fact = Fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            source_type=SourceType.ai_deduction,
            from_deduction_id=ded.id,
        )
        cm.invalidate_deduction("accept", ded, fact=fact)
        assert (char.id, loc.id, ts.id) not in cm.pending_index
        assert (char.id, loc.id, ts.id) in cm.fact_index
        assert (char.id, loc.id, ts.id) not in cm.rejection_index


# ---------------------------------------------------------------------------
# Tests: duplicate names in by-name indexes
# ---------------------------------------------------------------------------


class TestDuplicateNames:
    def test_char_by_name_duplicate_case_last_writer_wins(self):
        """Last-writer-wins for duplicate character names during rebuild."""
        proj = make_project()
        add_char(proj, "Alice")
        char2 = add_char(proj, "ALICE")
        cm = CacheManager()
        cm.rebuild(proj)
        # char2 is later, so last writer wins
        assert cm.char_by_name["alice"] is char2

    def test_loc_by_name_duplicate_case_last_writer_wins(self):
        """Last-writer-wins for duplicate location names during rebuild."""
        proj = make_project()
        add_loc(proj, "Castle")
        loc2 = add_loc(proj, "castle")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.loc_by_name["castle"] is loc2

    def test_ts_label_map_bare_label_unique_no_conflict(self):
        """ts_label_map with unique bare labels has no conflicts."""
        proj = make_project()
        ts1 = add_ts(proj, "08:00")
        ts2 = add_ts(proj, "12:00")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.ts_label_map["08:00"] == ts1.id
        assert cm.ts_label_map["12:00"] == ts2.id


# ---------------------------------------------------------------------------
# Tests: duplicate-name fallback on remove/update (CRITICAL bug fix)
# ---------------------------------------------------------------------------


class TestDuplicateNameFallbackOnRemove:
    """When removing the by-name 'winner' for a duplicate lowercase name,
    CacheManager should fall back to another entity with the same key."""

    def test_remove_char_by_name_winner_installs_fallback(self):
        """Remove the by-name winner → another char with same lowered name takes over."""
        proj = make_project()
        char_a = add_char(proj, "alice")  # first
        char_b = add_char(proj, "Alice")  # last-writer-wins after rebuild
        cm = CacheManager()
        cm.rebuild(proj)
        # After rebuild, char_b is the winner (last-writer-wins)
        assert cm.char_by_name["alice"] is char_b

        # Simulate removing char_b from the project list
        remaining = [char_a]
        cm.invalidate_character("remove", char_b, remaining_characters=remaining)
        # char_a should now be the fallback winner
        assert "alice" in cm.char_by_name
        assert cm.char_by_name["alice"] is char_a

    def test_remove_char_by_name_winner_no_remaining_clears_key(self):
        """Remove the only char with a given name → key is deleted entirely."""
        proj = make_project()
        char_a = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        cm.invalidate_character("remove", char_a, remaining_characters=[])
        assert "alice" not in cm.char_by_name

    def test_remove_char_non_winner_leaves_winner_intact(self):
        """Remove a char that is NOT the by-name winner → winner unchanged."""
        proj = make_project()
        char_a = add_char(proj, "alice")
        char_b = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.char_by_name["alice"] is char_b

        remaining = [char_b]
        cm.invalidate_character("remove", char_a, remaining_characters=remaining)
        # char_b is still the winner
        assert cm.char_by_name["alice"] is char_b

    def test_remove_loc_by_name_winner_installs_fallback(self):
        """Remove the by-name winner location → fallback to another with same key."""
        proj = make_project()
        loc_a = add_loc(proj, "library")
        loc_b = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.loc_by_name["library"] is loc_b

        remaining = [loc_a]
        cm.invalidate_location("remove", loc_b, remaining_locations=remaining)
        assert "library" in cm.loc_by_name
        assert cm.loc_by_name["library"] is loc_a

    def test_remove_loc_by_name_winner_no_remaining_clears_key(self):
        """Remove the only location with a given name → key deleted."""
        proj = make_project()
        loc = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)
        cm.invalidate_location("remove", loc, remaining_locations=[])
        assert "library" not in cm.loc_by_name

    def test_remove_loc_non_winner_leaves_winner_intact(self):
        """Remove a location NOT the winner → winner unchanged."""
        proj = make_project()
        loc_a = add_loc(proj, "library")
        loc_b = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.loc_by_name["library"] is loc_b

        remaining = [loc_b]
        cm.invalidate_location("remove", loc_a, remaining_locations=remaining)
        assert cm.loc_by_name["library"] is loc_b

    def test_remove_char_three_duplicates_picks_first_remaining(self):
        """With 3 chars sharing same lowered name, removing winner picks first remaining."""
        proj = make_project()
        char_a = add_char(proj, "alice")
        char_b = add_char(proj, "Alice")
        char_c = add_char(proj, "ALICE")
        cm = CacheManager()
        cm.rebuild(proj)
        # Last-writer-wins: char_c
        assert cm.char_by_name["alice"] is char_c

        remaining = [char_a, char_b]
        cm.invalidate_character("remove", char_c, remaining_characters=remaining)
        # First matching remaining entity becomes the new winner
        assert cm.char_by_name["alice"] is char_a


class TestDuplicateNameFallbackOnUpdate:
    """When updating a char/loc name and the old name was the by-name winner,
    CacheManager should fall back to another entity with the same old name."""

    def test_update_char_name_installs_fallback_for_old_name(self):
        """Rename char that is the by-name winner → another char takes over old key."""
        proj = make_project()
        char_a = add_char(proj, "alice")
        char_b = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.char_by_name["alice"] is char_b

        # Rename char_b from "Alice" → "Betty"
        char_b.name = "Betty"
        cm.invalidate_character(
            "update", char_b, old_name="Alice", remaining_characters=[char_a, char_b]
        )
        # Old key "alice" should now point to char_a
        assert cm.char_by_name["alice"] is char_a
        # New key "betty" should point to char_b
        assert cm.char_by_name["betty"] is char_b

    def test_update_char_name_no_fallback_clears_old_key(self):
        """Rename the only char with a name → old key disappears."""
        proj = make_project()
        char = add_char(proj, "Alice")
        cm = CacheManager()
        cm.rebuild(proj)

        char.name = "Betty"
        cm.invalidate_character("update", char, old_name="Alice", remaining_characters=[char])
        assert "alice" not in cm.char_by_name
        assert cm.char_by_name["betty"] is char

    def test_update_loc_name_installs_fallback_for_old_name(self):
        """Rename location that is the by-name winner → fallback for old key."""
        proj = make_project()
        loc_a = add_loc(proj, "library")
        loc_b = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)
        assert cm.loc_by_name["library"] is loc_b

        loc_b.name = "Archive"
        cm.invalidate_location(
            "update", loc_b, old_name="Library", remaining_locations=[loc_a, loc_b]
        )
        assert cm.loc_by_name["library"] is loc_a
        assert cm.loc_by_name["archive"] is loc_b

    def test_update_loc_name_no_fallback_clears_old_key(self):
        """Rename the only location with a name → old key disappears."""
        proj = make_project()
        loc = add_loc(proj, "Library")
        cm = CacheManager()
        cm.rebuild(proj)

        loc.name = "Archive"
        cm.invalidate_location("update", loc, old_name="Library", remaining_locations=[loc])
        assert "library" not in cm.loc_by_name
        assert cm.loc_by_name["archive"] is loc
