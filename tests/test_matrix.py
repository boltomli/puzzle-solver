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
from src.ui.pages.matrix import build_matrix_data


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
        rows = build_matrix_data(sample_project)
        assert len(rows) == 2  # 2 characters

        for row in rows:
            assert row["character"] in ("Alice", "Bob")
            for ts in ["14:00", "15:00", "16:00"]:
                assert row[ts] == ""
                assert row[f"{ts}_status"] == "unknown"

    def test_confirmed_fact(self, sample_project):
        """A confirmed fact should show location name with 'confirmed' status."""
        sample_project.facts.append(
            Fact(
                character_id="char-a",
                location_id="loc-lib",
                time_slot="14:00",
                source_type=SourceType.user_input,
            )
        )
        rows = build_matrix_data(sample_project)
        alice_row = next(r for r in rows if r["character"] == "Alice")

        assert alice_row["14:00"] == "图书馆"
        assert alice_row["14:00_status"] == "confirmed"
        # Other slots still unknown
        assert alice_row["15:00"] == ""
        assert alice_row["15:00_status"] == "unknown"

    def test_pending_deduction(self, sample_project):
        """A pending deduction should show location in parens with 'pending' status."""
        sample_project.deductions.append(
            Deduction(
                character_id="char-b",
                location_id="loc-kit",
                time_slot="15:00",
                confidence=ConfidenceLevel.high,
                reasoning="Test reasoning",
                status=DeductionStatus.pending,
            )
        )
        rows = build_matrix_data(sample_project)
        bob_row = next(r for r in rows if r["character"] == "Bob")

        assert bob_row["15:00"] == "(厨房)"
        assert bob_row["15:00_status"] == "pending"

    def test_fact_overrides_deduction(self, sample_project):
        """If both a fact and pending deduction exist for same cell, fact wins."""
        sample_project.facts.append(
            Fact(
                character_id="char-a",
                location_id="loc-lib",
                time_slot="14:00",
                source_type=SourceType.user_input,
            )
        )
        sample_project.deductions.append(
            Deduction(
                character_id="char-a",
                location_id="loc-kit",
                time_slot="14:00",
                confidence=ConfidenceLevel.medium,
                reasoning="Wrong deduction",
                status=DeductionStatus.pending,
            )
        )
        rows = build_matrix_data(sample_project)
        alice_row = next(r for r in rows if r["character"] == "Alice")

        # Fact takes precedence
        assert alice_row["14:00"] == "图书馆"
        assert alice_row["14:00_status"] == "confirmed"

    def test_accepted_deduction_not_shown_as_pending(self, sample_project):
        """An accepted deduction should not show as pending."""
        sample_project.deductions.append(
            Deduction(
                character_id="char-a",
                location_id="loc-lib",
                time_slot="14:00",
                confidence=ConfidenceLevel.certain,
                reasoning="Accepted",
                status=DeductionStatus.accepted,
            )
        )
        rows = build_matrix_data(sample_project)
        alice_row = next(r for r in rows if r["character"] == "Alice")

        # No fact exists, and deduction is accepted (not pending), so unknown
        assert alice_row["14:00"] == ""
        assert alice_row["14:00_status"] == "unknown"

    def test_multiple_characters_and_slots(self, sample_project):
        """Test a realistic mix of facts and deductions."""
        sample_project.facts.extend(
            [
                Fact(
                    character_id="char-a",
                    location_id="loc-lib",
                    time_slot="14:00",
                    source_type=SourceType.script_explicit,
                ),
                Fact(
                    character_id="char-b",
                    location_id="loc-gar",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
            ]
        )
        sample_project.deductions.append(
            Deduction(
                character_id="char-a",
                location_id="loc-kit",
                time_slot="15:00",
                confidence=ConfidenceLevel.high,
                reasoning="Deduced",
                status=DeductionStatus.pending,
            )
        )

        rows = build_matrix_data(sample_project)
        assert len(rows) == 2

        alice_row = next(r for r in rows if r["character"] == "Alice")
        bob_row = next(r for r in rows if r["character"] == "Bob")

        assert alice_row["14:00"] == "图书馆"
        assert alice_row["14:00_status"] == "confirmed"
        assert alice_row["15:00"] == "(厨房)"
        assert alice_row["15:00_status"] == "pending"
        assert alice_row["16:00"] == ""
        assert alice_row["16:00_status"] == "unknown"

        assert bob_row["14:00"] == "花园"
        assert bob_row["14:00_status"] == "confirmed"
        assert bob_row["15:00"] == ""
        assert bob_row["15:00_status"] == "unknown"

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
        rows = build_matrix_data(project)
        assert rows[0]["10:00"] == "?"
        assert rows[0]["10:00_status"] == "confirmed"

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
