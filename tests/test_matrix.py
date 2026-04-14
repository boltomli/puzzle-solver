"""Tests for the matrix data building logic."""

import pytest

from src.models.puzzle import (
    Character,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    Fact,
    Location,
    Project,
    SourceType,
)
from src.ui.pages.matrix import build_location_time_data, build_matrix_data


@pytest.fixture
def sample_project():
    """Create a sample project with characters, locations, time slots."""
    char_a = Character(id="char-a", name="Alice")
    char_b = Character(id="char-b", name="Bob")
    loc_lib = Location(id="loc-lib", name="图书馆")
    loc_kit = Location(id="loc-kit", name="厨房")
    loc_gar = Location(id="loc-gar", name="花园")

    project = Project(
        name="Test Mystery",
        time_slots=["14:00", "15:00", "16:00"],
        characters=[char_a, char_b],
        locations=[loc_lib, loc_kit, loc_gar],
    )
    return project


class TestBuildMatrixData:
    def test_empty_matrix(self, sample_project):
        """All cells should be unknown when no facts or deductions exist."""
        ts_map = {ts.label: ts for ts in sample_project.time_slots}
        rows = build_matrix_data(sample_project)
        assert len(rows) == 2  # 2 characters

        for row in rows:
            assert row["character"] in ("Alice", "Bob")
            for label in ["14:00", "15:00", "16:00"]:
                ts_id = ts_map[label].id
                assert row[ts_id] == ""
                assert row[f"{ts_id}_status"] == "unknown"

    def test_confirmed_fact(self, sample_project):
        """A confirmed fact should show location name with 'confirmed' status."""
        ts_map = {ts.label: ts for ts in sample_project.time_slots}
        sample_project.facts.append(
            Fact(
                character_id="char-a",
                location_id="loc-lib",
                time_slot=ts_map["14:00"].id,
                source_type=SourceType.user_input,
            )
        )
        rows = build_matrix_data(sample_project)
        alice_row = next(r for r in rows if r["character"] == "Alice")

        assert alice_row[ts_map["14:00"].id] == "图书馆"
        assert alice_row[f"{ts_map['14:00'].id}_status"] == "confirmed"
        # Other slots still unknown
        assert alice_row[ts_map["15:00"].id] == ""
        assert alice_row[f"{ts_map['15:00'].id}_status"] == "unknown"

    def test_pending_deduction(self, sample_project):
        """A pending deduction should show location in parens with 'pending' status."""
        ts_map = {ts.label: ts for ts in sample_project.time_slots}
        sample_project.deductions.append(
            Deduction(
                character_id="char-b",
                location_id="loc-kit",
                time_slot=ts_map["15:00"].id,
                confidence=ConfidenceLevel.high,
                reasoning="Test reasoning",
                status=DeductionStatus.pending,
            )
        )
        rows = build_matrix_data(sample_project)
        bob_row = next(r for r in rows if r["character"] == "Bob")

        assert bob_row[ts_map["15:00"].id] == "(厨房)"
        assert bob_row[f"{ts_map['15:00'].id}_status"] == "pending"

    def test_fact_overrides_deduction(self, sample_project):
        """If both a fact and pending deduction exist for same cell, fact wins."""
        ts_map = {ts.label: ts for ts in sample_project.time_slots}
        sample_project.facts.append(
            Fact(
                character_id="char-a",
                location_id="loc-lib",
                time_slot=ts_map["14:00"].id,
                source_type=SourceType.user_input,
            )
        )
        sample_project.deductions.append(
            Deduction(
                character_id="char-a",
                location_id="loc-kit",
                time_slot=ts_map["14:00"].id,
                confidence=ConfidenceLevel.medium,
                reasoning="Wrong deduction",
                status=DeductionStatus.pending,
            )
        )
        rows = build_matrix_data(sample_project)
        alice_row = next(r for r in rows if r["character"] == "Alice")

        # Fact takes precedence
        assert alice_row[ts_map["14:00"].id] == "图书馆"
        assert alice_row[f"{ts_map['14:00'].id}_status"] == "confirmed"

    def test_accepted_deduction_not_shown_as_pending(self, sample_project):
        """An accepted deduction should not show as pending."""
        ts_map = {ts.label: ts for ts in sample_project.time_slots}
        sample_project.deductions.append(
            Deduction(
                character_id="char-a",
                location_id="loc-lib",
                time_slot=ts_map["14:00"].id,
                confidence=ConfidenceLevel.certain,
                reasoning="Accepted",
                status=DeductionStatus.accepted,
            )
        )
        rows = build_matrix_data(sample_project)
        alice_row = next(r for r in rows if r["character"] == "Alice")

        # No fact exists, and deduction is accepted (not pending), so unknown
        assert alice_row[ts_map["14:00"].id] == ""
        assert alice_row[f"{ts_map['14:00'].id}_status"] == "unknown"

    def test_multiple_characters_and_slots(self, sample_project):
        """Test a realistic mix of facts and deductions."""
        ts_map = {ts.label: ts for ts in sample_project.time_slots}
        sample_project.facts.extend(
            [
                Fact(
                    character_id="char-a",
                    location_id="loc-lib",
                    time_slot=ts_map["14:00"].id,
                    source_type=SourceType.script_explicit,
                ),
                Fact(
                    character_id="char-b",
                    location_id="loc-gar",
                    time_slot=ts_map["14:00"].id,
                    source_type=SourceType.user_input,
                ),
            ]
        )
        sample_project.deductions.append(
            Deduction(
                character_id="char-a",
                location_id="loc-kit",
                time_slot=ts_map["15:00"].id,
                confidence=ConfidenceLevel.high,
                reasoning="Deduced",
                status=DeductionStatus.pending,
            )
        )

        rows = build_matrix_data(sample_project)
        assert len(rows) == 2

        alice_row = next(r for r in rows if r["character"] == "Alice")
        bob_row = next(r for r in rows if r["character"] == "Bob")

        assert alice_row[ts_map["14:00"].id] == "图书馆"
        assert alice_row[f"{ts_map['14:00'].id}_status"] == "confirmed"
        assert alice_row[ts_map["15:00"].id] == "(厨房)"
        assert alice_row[f"{ts_map['15:00'].id}_status"] == "pending"
        assert alice_row[ts_map["16:00"].id] == ""
        assert alice_row[f"{ts_map['16:00'].id}_status"] == "unknown"

        assert bob_row[ts_map["14:00"].id] == "花园"
        assert bob_row[f"{ts_map['14:00'].id}_status"] == "confirmed"
        assert bob_row[ts_map["15:00"].id] == ""
        assert bob_row[f"{ts_map['15:00'].id}_status"] == "unknown"

    def test_unknown_location_id(self):
        """If a fact references a non-existent location, show '?'."""
        project = Project(
            name="Test",
            time_slots=["10:00"],
            characters=[Character(id="c1", name="Charlie")],
            locations=[],
            facts=[
                Fact(
                    character_id="c1",
                    location_id="nonexistent",
                    time_slot="10:00",
                    source_type=SourceType.user_input,
                )
            ],
        )
        ts_map = {ts.label: ts for ts in project.time_slots}
        rows = build_matrix_data(project)
        assert rows[0][ts_map["10:00"].id] == "?"
        assert rows[0][f"{ts_map['10:00'].id}_status"] == "confirmed"

    def test_no_characters_returns_empty(self):
        """No characters means no rows."""
        project = Project(
            name="Empty",
            time_slots=["10:00"],
            characters=[],
            locations=[Location(id="l1", name="Room")],
        )
        rows = build_matrix_data(project)
        assert rows == []

    def test_no_time_slots_returns_minimal(self):
        """No time slots means rows with only character key."""
        project = Project(
            name="No Slots",
            time_slots=[],
            characters=[Character(id="c1", name="Dan")],
            locations=[],
        )
        rows = build_matrix_data(project)
        assert len(rows) == 1
        assert rows[0]["character"] == "Dan"
        assert rows[0]["id"] == "c1"

    def test_row_ids_match_characters(self, sample_project):
        """Each row 'id' should match the corresponding character id."""
        rows = build_matrix_data(sample_project)
        ids = {r["id"] for r in rows}
        assert ids == {"char-a", "char-b"}


class TestBuildLocationTimeData:
    """Tests for the build_location_time_data() pure function."""

    @pytest.fixture
    def loc_project(self):
        """A project with two characters, two locations, and two time slots."""
        char_a = Character(id="char-a", name="Alice")
        char_b = Character(id="char-b", name="Bob")
        loc_lib = Location(id="loc-lib", name="图书馆")
        loc_kit = Location(id="loc-kit", name="厨房")

        return Project(
            name="Loc Test",
            time_slots=["14:00", "15:00"],
            characters=[char_a, char_b],
            locations=[loc_lib, loc_kit],
        )

    def test_returns_list_of_dicts(self, loc_project):
        """build_location_time_data should return a list of dicts."""
        result = build_location_time_data(loc_project)
        assert isinstance(result, list)
        for row in result:
            assert isinstance(row, dict)

    def test_row_keys(self, loc_project):
        """Each row must have 'id', 'location', and one key per time slot."""
        ts_map = {ts.label: ts for ts in loc_project.time_slots}
        result = build_location_time_data(loc_project)
        assert len(result) == 2  # 2 locations
        for row in result:
            assert "id" in row
            assert "location" in row
            for label in ["14:00", "15:00"]:
                ts_id = ts_map[label].id
                assert ts_id in row
                assert f"{ts_id}_status" in row

    def test_confirmed_fact_shows_character(self, loc_project):
        """A confirmed fact at (loc, time) should show character name; status=confirmed."""
        ts_map = {ts.label: ts for ts in loc_project.time_slots}
        loc_project.facts.append(
            Fact(
                character_id="char-a",
                location_id="loc-lib",
                time_slot=ts_map["14:00"].id,
                source_type=SourceType.user_input,
            )
        )
        result = build_location_time_data(loc_project)
        lib_row = next(r for r in result if r["id"] == "loc-lib")

        assert lib_row[ts_map["14:00"].id] == "Alice"
        assert lib_row[f"{ts_map['14:00'].id}_status"] == "confirmed"
        # Other slot is unknown
        assert lib_row[ts_map["15:00"].id] == ""
        assert lib_row[f"{ts_map['15:00'].id}_status"] == "unknown"

    def test_pending_shows_parenthesized(self, loc_project):
        """A pending deduction should show character name in parentheses; status=pending."""
        ts_map = {ts.label: ts for ts in loc_project.time_slots}
        loc_project.deductions.append(
            Deduction(
                character_id="char-b",
                location_id="loc-kit",
                time_slot=ts_map["15:00"].id,
                confidence=ConfidenceLevel.high,
                reasoning="Deduced",
                status=DeductionStatus.pending,
            )
        )
        result = build_location_time_data(loc_project)
        kit_row = next(r for r in result if r["id"] == "loc-kit")

        assert kit_row[ts_map["15:00"].id] == "(Bob)"
        assert kit_row[f"{ts_map['15:00'].id}_status"] == "pending"

    def test_multi_character_cell(self, loc_project):
        """Two characters at the same (location, time_slot) should be comma-separated."""
        ts_map = {ts.label: ts for ts in loc_project.time_slots}
        loc_project.facts.extend(
            [
                Fact(
                    character_id="char-a",
                    location_id="loc-lib",
                    time_slot=ts_map["14:00"].id,
                    source_type=SourceType.user_input,
                ),
                Fact(
                    character_id="char-b",
                    location_id="loc-lib",
                    time_slot=ts_map["14:00"].id,
                    source_type=SourceType.user_input,
                ),
            ]
        )
        result = build_location_time_data(loc_project)
        lib_row = next(r for r in result if r["id"] == "loc-lib")

        # Both character names should appear, comma-separated
        cell_value = lib_row[ts_map["14:00"].id]
        assert "Alice" in cell_value
        assert "Bob" in cell_value
        assert lib_row[f"{ts_map['14:00'].id}_status"] == "confirmed"

    def test_no_locations_empty(self):
        """Returns empty list when the project has no locations."""
        project = Project(
            name="No Locs",
            time_slots=["14:00"],
            characters=[Character(id="c1", name="Charlie")],
            locations=[],
        )
        result = build_location_time_data(project)
        assert result == []

    def test_confirmed_and_pending_combined(self, loc_project):
        """When both confirmed and pending chars exist at same (loc, time), status is confirmed."""
        ts_map = {ts.label: ts for ts in loc_project.time_slots}
        loc_project.facts.append(
            Fact(
                character_id="char-a",
                location_id="loc-lib",
                time_slot=ts_map["14:00"].id,
                source_type=SourceType.user_input,
            )
        )
        loc_project.deductions.append(
            Deduction(
                character_id="char-b",
                location_id="loc-lib",
                time_slot=ts_map["14:00"].id,
                confidence=ConfidenceLevel.medium,
                reasoning="Pending Bob",
                status=DeductionStatus.pending,
            )
        )
        result = build_location_time_data(loc_project)
        lib_row = next(r for r in result if r["id"] == "loc-lib")

        # Confirmed Alice + pending Bob in parens
        cell_value = lib_row[ts_map["14:00"].id]
        assert "Alice" in cell_value
        assert "(Bob)" in cell_value
        # Status should be confirmed since there's a confirmed fact
        assert lib_row[f"{ts_map['14:00'].id}_status"] == "confirmed"

    def test_row_id_and_location_name(self, loc_project):
        """Each row 'id' and 'location' should match the actual location data."""
        result = build_location_time_data(loc_project)
        ids = {r["id"] for r in result}
        names = {r["location"] for r in result}
        assert ids == {"loc-lib", "loc-kit"}
        assert names == {"图书馆", "厨房"}
