"""Tests for the DeductionService cascade elimination logic."""

import pytest

from src.models.puzzle import (
    Character,
    ConfidenceLevel,
    Deduction,
    Fact,
    Location,
    Project,
    Rejection,
    SourceType,
)
from src.services.deduction import DeductionService, _extract_json


@pytest.fixture
def three_by_three_project():
    """3 characters × 3 locations × 3 time slots for testing."""
    return Project(
        name="3x3 Test",
        time_slots=["14:00", "15:00", "16:00"],
        characters=[
            Character(id="c1", name="Alice"),
            Character(id="c2", name="Bob"),
            Character(id="c3", name="Charlie"),
        ],
        locations=[
            Location(id="l1", name="图书馆"),
            Location(id="l2", name="厨房"),
            Location(id="l3", name="花园"),
        ],
    )


class TestCascadeDeduction:
    def test_no_deductions_when_nothing_filled(self, three_by_three_project):
        """With no facts or rejections, cascade should find nothing."""
        results = DeductionService.run_cascade(three_by_three_project)
        assert results == []

    def test_single_location_remaining_for_character(self, three_by_three_project):
        """If 2 of 3 locations are taken by others at a time, remaining char gets last one."""
        proj = three_by_three_project
        # At 14:00: Bob is in 图书馆, Charlie is in 厨房
        proj.facts.extend(
            [
                Fact(
                    character_id="c2",
                    location_id="l1",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
                Fact(
                    character_id="c3",
                    location_id="l2",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
            ]
        )
        results = DeductionService.run_cascade(proj)

        # Alice must be in 花园 at 14:00
        assert len(results) >= 1
        alice_14 = next(
            (d for d in results if d.character_id == "c1" and d.time_slot == "14:00"),
            None,
        )
        assert alice_14 is not None
        assert alice_14.location_id == "l3"
        assert alice_14.confidence == ConfidenceLevel.certain
        assert "消元法" in alice_14.reasoning

    def test_single_character_remaining_for_location(self, three_by_three_project):
        """If 2 of 3 characters are placed elsewhere at a time, remaining gets the location."""
        proj = three_by_three_project
        # At 15:00: Alice is in 图书馆, Bob is in 花园
        proj.facts.extend(
            [
                Fact(
                    character_id="c1",
                    location_id="l1",
                    time_slot="15:00",
                    source_type=SourceType.user_input,
                ),
                Fact(
                    character_id="c2",
                    location_id="l3",
                    time_slot="15:00",
                    source_type=SourceType.user_input,
                ),
            ]
        )
        results = DeductionService.run_cascade(proj)

        # Charlie must be in 厨房 at 15:00
        charlie_15 = next(
            (d for d in results if d.character_id == "c3" and d.time_slot == "15:00"),
            None,
        )
        assert charlie_15 is not None
        assert charlie_15.location_id == "l2"
        assert charlie_15.confidence == ConfidenceLevel.certain

    def test_rejection_enables_elimination(self, three_by_three_project):
        """Rejection + occupancy should enable elimination."""
        proj = three_by_three_project
        # At 14:00: Bob is in 图书馆
        proj.facts.append(
            Fact(
                character_id="c2",
                location_id="l1",
                time_slot="14:00",
                source_type=SourceType.user_input,
            )
        )
        # Alice is rejected from 厨房 at 14:00
        proj.rejections.append(
            Rejection(
                character_id="c1",
                location_id="l2",
                time_slot="14:00",
                reason="Test rejection",
            )
        )

        results = DeductionService.run_cascade(proj)

        # Alice: 图书馆 occupied by Bob, 厨房 rejected → must be 花园
        alice_14 = next(
            (d for d in results if d.character_id == "c1" and d.time_slot == "14:00"),
            None,
        )
        assert alice_14 is not None
        assert alice_14.location_id == "l3"  # 花园
        assert alice_14.confidence == ConfidenceLevel.certain

    def test_no_duplicate_deductions(self, three_by_three_project):
        """Both strategies should not produce the same deduction twice."""
        proj = three_by_three_project
        # Fill enough to trigger both strategies for same cell
        proj.facts.extend(
            [
                Fact(
                    character_id="c2",
                    location_id="l1",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
                Fact(
                    character_id="c3",
                    location_id="l2",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
            ]
        )
        results = DeductionService.run_cascade(proj)

        # Alice at 花园 at 14:00 should appear exactly once
        alice_14_deds = [
            d
            for d in results
            if d.character_id == "c1"
            and d.location_id == "l3"
            and d.time_slot == "14:00"
        ]
        assert len(alice_14_deds) == 1

    def test_already_filled_slots_skipped(self, three_by_three_project):
        """Slots with existing facts should not generate deductions."""
        proj = three_by_three_project
        # Fill all slots for 14:00
        proj.facts.extend(
            [
                Fact(
                    character_id="c1",
                    location_id="l1",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
                Fact(
                    character_id="c2",
                    location_id="l2",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
                Fact(
                    character_id="c3",
                    location_id="l3",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
            ]
        )
        results = DeductionService.run_cascade(proj)

        # No deductions for 14:00 since it's fully filled
        for d in results:
            assert d.time_slot != "14:00"

    def test_multiple_rejections(self, three_by_three_project):
        """Multiple rejections can narrow down to single option."""
        proj = three_by_three_project
        # At 14:00: reject Alice from 图书馆 and 厨房
        proj.rejections.extend(
            [
                Rejection(
                    character_id="c1",
                    location_id="l1",
                    time_slot="14:00",
                    reason="Not here",
                ),
                Rejection(
                    character_id="c1",
                    location_id="l2",
                    time_slot="14:00",
                    reason="Not here either",
                ),
            ]
        )
        results = DeductionService.run_cascade(proj)

        # Alice must be at 花园 at 14:00
        alice_14 = next(
            (d for d in results if d.character_id == "c1" and d.time_slot == "14:00"),
            None,
        )
        assert alice_14 is not None
        assert alice_14.location_id == "l3"

    def test_no_certain_when_multiple_possibilities(self, three_by_three_project):
        """If 2+ locations remain, no certain deduction should be made."""
        proj = three_by_three_project
        # At 14:00: only Bob is placed, 2 locations remain for Alice
        proj.facts.append(
            Fact(
                character_id="c2",
                location_id="l1",
                time_slot="14:00",
                source_type=SourceType.user_input,
            )
        )
        results = DeductionService.run_cascade(proj)

        # Alice still has 2 possibilities (厨房, 花园), should not get deduction
        alice_14 = next(
            (d for d in results if d.character_id == "c1" and d.time_slot == "14:00"),
            None,
        )
        assert alice_14 is None

    def test_empty_project(self):
        """Empty project should produce no deductions."""
        proj = Project(name="Empty")
        results = DeductionService.run_cascade(proj)
        assert results == []

    def test_two_by_two_complete_fill(self):
        """In a 2×2 grid with 1 fact, cascade fills remaining 3 cells."""
        proj = Project(
            name="2x2",
            time_slots=["10:00", "11:00"],
            characters=[
                Character(id="ca", name="A"),
                Character(id="cb", name="B"),
            ],
            locations=[
                Location(id="la", name="X"),
                Location(id="lb", name="Y"),
            ],
            facts=[
                Fact(
                    character_id="ca",
                    location_id="la",
                    time_slot="10:00",
                    source_type=SourceType.user_input,
                ),
            ],
        )
        results = DeductionService.run_cascade(proj)

        # B must be at Y at 10:00 (only remaining location)
        b_10 = next(
            (d for d in results if d.character_id == "cb" and d.time_slot == "10:00"),
            None,
        )
        assert b_10 is not None
        assert b_10.location_id == "lb"

    def test_cascade_deduction_type(self, three_by_three_project):
        """Deductions should be of type Deduction with correct fields."""
        proj = three_by_three_project
        proj.facts.extend(
            [
                Fact(
                    character_id="c2",
                    location_id="l1",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
                Fact(
                    character_id="c3",
                    location_id="l2",
                    time_slot="14:00",
                    source_type=SourceType.user_input,
                ),
            ]
        )
        results = DeductionService.run_cascade(proj)

        for d in results:
            assert isinstance(d, Deduction)
            assert d.confidence == ConfidenceLevel.certain
            assert d.character_id
            assert d.location_id
            assert d.time_slot
            assert d.reasoning


class TestExtractJson:
    """Tests for _extract_json helper that handles markdown-wrapped LLM responses."""

    def test_clean_json(self):
        """Clean JSON string parses correctly."""
        assert _extract_json('{"key": "value"}') == {"key": "value"}

    def test_json_in_code_fence_with_lang(self):
        """JSON wrapped in ```json ... ``` extracts and parses."""
        raw = '```json\n{"key": "value"}\n```'
        assert _extract_json(raw) == {"key": "value"}

    def test_json_in_code_fence_no_lang(self):
        """JSON wrapped in ``` ... ``` (no language tag) extracts and parses."""
        raw = '```\n{"key": "value"}\n```'
        assert _extract_json(raw) == {"key": "value"}

    def test_json_with_surrounding_text(self):
        """JSON with leading/trailing text but valid { } block extracts."""
        raw = 'Here is the result:\n{"key": "value"}\nDone.'
        assert _extract_json(raw) == {"key": "value"}

    def test_invalid_content_raises(self):
        """Completely invalid content raises ValueError."""
        with pytest.raises(ValueError, match="无法从 AI 响应中提取有效 JSON"):
            _extract_json("no json here at all")

    def test_empty_string_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="无法从 AI 响应中提取有效 JSON"):
            _extract_json("")
