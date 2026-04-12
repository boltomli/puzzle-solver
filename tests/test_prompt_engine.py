"""Tests for the PromptEngine prompt assembly."""

import pytest

from src.models.puzzle import (
    Character,
    CharacterStatus,
    ConfidenceLevel,
    Deduction,
    Fact,
    Hint,
    HintType,
    Location,
    Project,
    Rejection,
    Script,
    ScriptMetadata,
    SourceType,
)
from src.services.prompt_engine import PromptEngine


@pytest.fixture
def engine():
    return PromptEngine()


@pytest.fixture
def sample_project():
    """A populated project for prompt testing."""
    return Project(
        name="庄园谋杀案",
        description="一场发生在乡村庄园的谋杀案",
        time_slots=["14:00", "15:00", "16:00"],
        characters=[
            Character(
                id="char-001",
                name="维多利亚夫人",
                aliases=["Victoria", "夫人"],
                description="庄园女主人",
                status=CharacterStatus.confirmed,
            ),
            Character(
                id="char-002",
                name="芥末上校",
                aliases=["上校"],
                status=CharacterStatus.confirmed,
            ),
        ],
        locations=[
            Location(id="loc-001", name="图书馆", aliases=["Library"]),
            Location(id="loc-002", name="厨房"),
            Location(id="loc-003", name="花园", aliases=["Garden"]),
        ],
        scripts=[
            Script(
                id="script-001",
                title="第一幕",
                raw_text="维多利亚夫人在下午两点正在图书馆读书。",
                metadata=ScriptMetadata(
                    source_order=1,
                    stated_time="14:00",
                    stated_location="图书馆",
                ),
            ),
        ],
        facts=[
            Fact(
                id="fact-001",
                character_id="char-001",
                location_id="loc-001",
                time_slot="14:00",
                source_type=SourceType.script_explicit,
                source_evidence="Script #1",
            ),
        ],
        rejections=[
            Rejection(
                id="rej-001",
                character_id="char-002",
                location_id="loc-003",
                time_slot="15:00",
                reason="上校的膝伤无法走到花园",
            ),
        ],
        hints=[
            Hint(
                id="hint-001",
                type=HintType.rule,
                content="每个人每个时间段只能在一个地点",
            ),
            Hint(
                id="hint-002",
                type=HintType.hint,
                content="维多利亚夫人从不进厨房",
            ),
        ],
    )


class TestDeductionPrompt:
    def test_returns_tuple(self, engine, sample_project):
        """build_deduction_prompt should return (system_prompt, user_prompt)."""
        result = engine.build_deduction_prompt(sample_project)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_system_prompt_not_empty(self, engine, sample_project):
        """System prompt should be non-empty."""
        system_prompt, _ = engine.build_deduction_prompt(sample_project)
        assert len(system_prompt) > 100
        assert "deduction" in system_prompt.lower()

    def test_user_prompt_contains_game_name(self, engine, sample_project):
        """User prompt should include the game name."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "庄园谋杀案" in user_prompt

    def test_user_prompt_contains_description(self, engine, sample_project):
        """User prompt should include the project description."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "乡村庄园" in user_prompt

    def test_user_prompt_contains_time_slots(self, engine, sample_project):
        """User prompt should list all time slots."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "14:00" in user_prompt
        assert "15:00" in user_prompt
        assert "16:00" in user_prompt

    def test_user_prompt_contains_characters(self, engine, sample_project):
        """User prompt should list all characters with IDs and aliases."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "维多利亚夫人" in user_prompt
        assert "char-001" in user_prompt
        assert "Victoria" in user_prompt
        assert "芥末上校" in user_prompt
        assert "char-002" in user_prompt

    def test_user_prompt_contains_character_descriptions(self, engine, sample_project):
        """User prompt should include character descriptions."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "庄园女主人" in user_prompt

    def test_user_prompt_contains_locations(self, engine, sample_project):
        """User prompt should list all locations with aliases."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "图书馆" in user_prompt
        assert "loc-001" in user_prompt
        assert "Library" in user_prompt
        assert "厨房" in user_prompt
        assert "花园" in user_prompt

    def test_user_prompt_contains_hints(self, engine, sample_project):
        """User prompt should include game rules and hints."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "[RULE]" in user_prompt
        assert "每个人每个时间段只能在一个地点" in user_prompt
        assert "[HINT]" in user_prompt
        assert "从不进厨房" in user_prompt

    def test_user_prompt_contains_confirmed_facts(self, engine, sample_project):
        """User prompt should list confirmed facts with character/location names."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "✅" in user_prompt
        assert "维多利亚夫人" in user_prompt
        assert "图书馆" in user_prompt
        assert "14:00" in user_prompt

    def test_user_prompt_contains_rejections(self, engine, sample_project):
        """User prompt should list rejected deductions."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "❌" in user_prompt
        assert "芥末上校" in user_prompt
        assert "花园" in user_prompt
        assert "15:00" in user_prompt
        assert "膝伤" in user_prompt

    def test_user_prompt_contains_unfilled_slots(self, engine, sample_project):
        """User prompt should list unfilled slots."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        # Victoria has fact for 14:00 but not 15:00/16:00
        assert "维多利亚夫人 at 15:00: ???" in user_prompt
        assert "维多利亚夫人 at 16:00: ???" in user_prompt
        # Colonel has no facts
        assert "芥末上校 at 14:00: ???" in user_prompt
        assert "芥末上校 at 15:00: ???" in user_prompt
        assert "芥末上校 at 16:00: ???" in user_prompt

    def test_user_prompt_does_not_list_filled_as_unfilled(self, engine, sample_project):
        """Filled slots should NOT appear in UNFILLED SLOTS section."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        # Victoria at 14:00 is confirmed, should not be in unfilled
        assert "维多利亚夫人 at 14:00: ???" not in user_prompt

    def test_user_prompt_contains_scripts(self, engine, sample_project):
        """User prompt should include script text."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "第一幕" in user_prompt
        assert "维多利亚夫人在下午两点正在图书馆读书" in user_prompt

    def test_user_prompt_contains_script_metadata(self, engine, sample_project):
        """User prompt should include script metadata."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "Stated time: 14:00" in user_prompt
        assert "Stated location: 图书馆" in user_prompt

    def test_user_prompt_contains_json_format(self, engine, sample_project):
        """User prompt should include the expected JSON response format."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert '"deductions"' in user_prompt
        assert '"character_id"' in user_prompt
        assert '"confidence"' in user_prompt
        assert '"reasoning"' in user_prompt

    def test_user_prompt_contains_task_instruction(self, engine, sample_project):
        """User prompt should end with task instructions."""
        _, user_prompt = engine.build_deduction_prompt(sample_project)
        assert "YOUR TASK" in user_prompt
        assert "CERTAIN" in user_prompt or "certain" in user_prompt

    def test_empty_project(self, engine):
        """Prompt should work for a minimal project."""
        project = Project(name="Empty Game")
        system_prompt, user_prompt = engine.build_deduction_prompt(project)
        assert "Empty Game" in user_prompt
        assert len(system_prompt) > 0

    def test_no_rejections(self, engine):
        """Prompt should include REJECTED section even when empty."""
        project = Project(
            name="No Rej",
            time_slots=["10:00"],
            characters=[Character(id="c1", name="A")],
            locations=[Location(id="l1", name="Room")],
        )
        _, user_prompt = engine.build_deduction_prompt(project)
        assert "REJECTED" in user_prompt


class TestScriptAnalysisPrompt:
    def test_returns_tuple(self, engine, sample_project):
        script = sample_project.scripts[0]
        result = engine.build_script_analysis_prompt(sample_project, script)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_contains_script_text(self, engine, sample_project):
        script = sample_project.scripts[0]
        _, user_prompt = engine.build_script_analysis_prompt(sample_project, script)
        assert "维多利亚夫人在下午两点正在图书馆读书" in user_prompt

    def test_contains_known_characters(self, engine, sample_project):
        script = sample_project.scripts[0]
        _, user_prompt = engine.build_script_analysis_prompt(sample_project, script)
        assert "维多利亚夫人" in user_prompt
        assert "芥末上校" in user_prompt

    def test_contains_known_locations(self, engine, sample_project):
        script = sample_project.scripts[0]
        _, user_prompt = engine.build_script_analysis_prompt(sample_project, script)
        assert "图书馆" in user_prompt
        assert "厨房" in user_prompt

    def test_contains_time_slots(self, engine, sample_project):
        script = sample_project.scripts[0]
        _, user_prompt = engine.build_script_analysis_prompt(sample_project, script)
        assert "14:00" in user_prompt

    def test_contains_json_format(self, engine, sample_project):
        script = sample_project.scripts[0]
        _, user_prompt = engine.build_script_analysis_prompt(sample_project, script)
        assert '"characters_mentioned"' in user_prompt
        assert '"locations_mentioned"' in user_prompt
        assert '"direct_facts"' in user_prompt

    def test_system_prompt_mentions_analyzer(self, engine, sample_project):
        script = sample_project.scripts[0]
        system_prompt, _ = engine.build_script_analysis_prompt(sample_project, script)
        assert "analyzer" in system_prompt.lower() or "script" in system_prompt.lower()
