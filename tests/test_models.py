"""Tests for Pydantic data models."""

import pytest
from datetime import datetime

from src.models.puzzle import (
    Character,
    CharacterStatus,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    Fact,
    Hint,
    HintScope,
    HintType,
    Location,
    Project,
    ProjectSummary,
    Rejection,
    Script,
    ScriptMetadata,
    SourceType,
)


class TestCharacter:
    def test_create_with_defaults(self):
        c = Character(name="Alice")
        assert c.name == "Alice"
        assert c.id  # auto-generated UUID
        assert c.status == CharacterStatus.confirmed
        assert c.aliases == []
        assert c.description is None
        assert isinstance(c.created_at, datetime)

    def test_create_with_all_fields(self):
        c = Character(
            name="Bob",
            aliases=["Robert", "Bobby"],
            description="A suspicious gardener",
            status=CharacterStatus.suspected,
            discovered_in_script_id="script-123",
        )
        assert c.name == "Bob"
        assert len(c.aliases) == 2
        assert c.status == CharacterStatus.suspected

    def test_json_roundtrip(self):
        c = Character(name="Charlie", aliases=["Chuck"])
        json_str = c.model_dump_json()
        c2 = Character.model_validate_json(json_str)
        assert c2.name == c.name
        assert c2.id == c.id
        assert c2.aliases == c.aliases


class TestLocation:
    def test_create_with_defaults(self):
        loc = Location(name="Library")
        assert loc.name == "Library"
        assert loc.id
        assert loc.aliases == []

    def test_json_roundtrip(self):
        loc = Location(name="Kitchen", aliases=["厨房"])
        json_str = loc.model_dump_json()
        loc2 = Location.model_validate_json(json_str)
        assert loc2.name == loc.name
        assert loc2.aliases == ["厨房"]


class TestScript:
    def test_create_with_defaults(self):
        s = Script(raw_text="This is a test script.")
        assert s.raw_text == "This is a test script."
        assert s.title is None
        assert isinstance(s.metadata, ScriptMetadata)

    def test_create_with_metadata(self):
        s = Script(
            title="Scene 1",
            raw_text="Alice enters the library.",
            metadata=ScriptMetadata(
                stated_time="15:00",
                stated_location="Library",
                characters_mentioned=["char-001"],
                source_order=1,
            ),
        )
        assert s.metadata.stated_time == "15:00"
        assert s.metadata.source_order == 1

    def test_json_roundtrip(self):
        s = Script(title="Test", raw_text="content")
        json_str = s.model_dump_json()
        s2 = Script.model_validate_json(json_str)
        assert s2.title == s.title
        assert s2.raw_text == s.raw_text


class TestFact:
    def test_create(self):
        f = Fact(
            character_id="char-001",
            location_id="loc-001",
            time_slot="15:00",
            source_type=SourceType.script_explicit,
            source_evidence="Script says Alice was in the Library at 3 PM.",
        )
        assert f.time_slot == "15:00"
        assert f.source_type == SourceType.script_explicit

    def test_invalid_time_slot(self):
        with pytest.raises(Exception):
            Fact(
                character_id="char-001",
                location_id="loc-001",
                time_slot="invalid",
                source_type=SourceType.user_input,
            )

    def test_json_roundtrip(self):
        f = Fact(
            character_id="c1",
            location_id="l1",
            time_slot="14:00",
            source_type=SourceType.ai_deduction,
        )
        json_str = f.model_dump_json()
        f2 = Fact.model_validate_json(json_str)
        assert f2.character_id == f.character_id
        assert f2.time_slot == f.time_slot


class TestRejection:
    def test_create(self):
        r = Rejection(
            character_id="char-001",
            location_id="loc-001",
            time_slot="16:00",
            reason="Contradicted by script evidence",
        )
        assert r.reason == "Contradicted by script evidence"

    def test_invalid_time_slot(self):
        with pytest.raises(Exception):
            Rejection(
                character_id="c1",
                location_id="l1",
                time_slot="not-a-time",
                reason="bad",
            )


class TestDeduction:
    def test_create(self):
        d = Deduction(
            character_id="char-001",
            location_id="loc-001",
            time_slot="17:00",
            confidence=ConfidenceLevel.high,
            reasoning="Based on script evidence...",
        )
        assert d.status == DeductionStatus.pending
        assert d.confidence == ConfidenceLevel.high
        assert d.resolved_at is None

    def test_json_roundtrip(self):
        d = Deduction(
            character_id="c1",
            location_id="l1",
            time_slot="18:00",
            confidence=ConfidenceLevel.certain,
            reasoning="Only possibility by elimination.",
            supporting_script_ids=["s1", "s2"],
        )
        json_str = d.model_dump_json()
        d2 = Deduction.model_validate_json(json_str)
        assert d2.confidence == ConfidenceLevel.certain
        assert d2.supporting_script_ids == ["s1", "s2"]


class TestHint:
    def test_create_rule(self):
        h = Hint(
            type=HintType.rule,
            content="Each character is at exactly one location per time slot.",
        )
        assert h.type == HintType.rule
        assert isinstance(h.applies_to, HintScope)

    def test_create_with_scope(self):
        h = Hint(
            type=HintType.hint,
            content="Lady Victoria never enters the Kitchen.",
            applies_to=HintScope(character_ids=["char-001"], location_ids=["loc-002"]),
        )
        assert len(h.applies_to.character_ids) == 1


class TestProject:
    def test_create_minimal(self):
        p = Project(name="Test Game")
        assert p.name == "Test Game"
        assert p.time_slots == []
        assert p.characters == []
        assert p.locations == []
        assert p.scripts == []
        assert p.facts == []

    def test_create_with_time_slots(self):
        p = Project(
            name="Mystery",
            time_slots=["14:00", "15:00", "16:00"],
        )
        assert len(p.time_slots) == 3

    def test_invalid_time_slot_in_project(self):
        with pytest.raises(Exception):
            Project(name="Bad", time_slots=["invalid"])

    def test_full_roundtrip(self):
        """Test a complete project with nested objects serialization."""
        char = Character(name="Alice")
        loc = Location(name="Library")
        script = Script(title="Scene 1", raw_text="Alice enters the library.")
        hint = Hint(type=HintType.rule, content="One person per location per time.")
        fact = Fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot="14:00",
            source_type=SourceType.script_explicit,
            source_evidence="Direct statement in script.",
            source_script_ids=[script.id],
        )

        project = Project(
            name="Test Mystery",
            description="A test mystery game",
            time_slots=["14:00", "15:00", "16:00"],
            characters=[char],
            locations=[loc],
            scripts=[script],
            facts=[fact],
            hints=[hint],
        )

        # Serialize to JSON and back
        json_str = project.model_dump_json()
        project2 = Project.model_validate_json(json_str)

        assert project2.name == project.name
        assert project2.id == project.id
        assert len(project2.characters) == 1
        assert project2.characters[0].name == "Alice"
        assert len(project2.locations) == 1
        assert len(project2.facts) == 1
        assert project2.facts[0].time_slot == "14:00"
        assert project2.hints[0].type == HintType.rule


class TestProjectSummary:
    def test_create(self):
        s = ProjectSummary(
            id="test-id",
            name="Test",
            character_count=3,
            location_count=5,
            script_count=2,
            fact_count=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert s.character_count == 3
