"""End-to-end tests for the puzzle solver application."""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.models.puzzle import (
    Character,
    CharacterStatus,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    Fact,
    HintType,
    Location,
    Project,
    Rejection,
    SourceType,
)
from src.services.deduction import DeductionService
from src.storage.json_store import JsonStore
from src.ui.state import AppState


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    temp_dir = tempfile.mkdtemp(prefix="puzzle_e2e_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def state(temp_data_dir):
    """Create an AppState with a temporary data directory."""
    store = JsonStore(data_dir=temp_data_dir)
    return AppState(store=store)


@pytest.fixture
def mock_analysis_result():
    return {
        "characters_mentioned": [
            {"character_id": None, "name": "Emma", "is_new": True, "context": "坐在草坪上"}
        ],
        "locations_mentioned": [
            {"location_id": None, "name": "草坪", "is_new": True, "context": "Emma坐在此处"}
        ],
        "time_references": [
            {"time_slot": "15:00", "reference_text": "15:00", "is_explicit": True}
        ],
        "direct_facts": [
            {
                "character_name": "Emma",
                "location_name": "草坪",
                "time_slot": "15:00",
                "confidence": "certain",
                "evidence": "15:00，Emma 坐在草坪上",
            }
        ],
        "alias_candidates": [],
    }


class TestE2EFixtures:
    def test_state_fixture_works(self, state):
        assert state.current_project is None
        assert state.store is not None

    def test_mock_analysis_result_structure(self, mock_analysis_result):
        assert "characters_mentioned" in mock_analysis_result
        assert mock_analysis_result["characters_mentioned"][0]["name"] == "Emma"
        assert mock_analysis_result["direct_facts"][0]["time_slot"] == "15:00"


class TestCoreE2EFlow:
    def test_full_script_to_matrix_flow(self, state, mock_analysis_result):
        """Test: create_project → add_script → extract entities from analysis → add entities → add fact → verify matrix."""
        # Step 1: Create project
        project = state.create_project(name="E2E测试项目")
        assert state.current_project is not None
        assert state.current_project.name == "E2E测试项目"

        # Step 2: Add script
        script = state.add_script(
            raw_text="15:00，Emma 坐在草坪上",
            title="测试剧本"
        )
        assert len(state.current_project.scripts) == 1
        assert script.raw_text == "15:00，Emma 坐在草坪上"

        # Step 3: Simulate saving analysis result (as if AI analyzed it)
        saved = state.save_script_analysis(script.id, mock_analysis_result)
        assert saved is True
        assert script.analysis_result is not None

        # Step 4: Extract entities from analysis result and add them
        # (Simulating what the UI does when user clicks "Add All")
        for ch in mock_analysis_result["characters_mentioned"]:
            if ch.get("is_new"):
                state.add_character(name=ch["name"])
        for lo in mock_analysis_result["locations_mentioned"]:
            if lo.get("is_new"):
                state.add_location(name=lo["name"])
        for tr in mock_analysis_result["time_references"]:
            ts = tr.get("time_slot", "")
            if ts:
                state.add_time_slot(ts)

        assert len(state.current_project.characters) == 1
        assert state.current_project.characters[0].name == "Emma"
        assert len(state.current_project.locations) == 1
        assert state.current_project.locations[0].name == "草坪"
        assert "15:00" in state.current_project.time_slots

        # Step 5: Add fact from analysis direct_facts
        emma = state.current_project.characters[0]
        lawn = state.current_project.locations[0]
        fact = state.add_fact(
            character_id=emma.id,
            location_id=lawn.id,
            time_slot="15:00",
            source_type=SourceType.script_explicit,
            source_evidence="15:00，Emma 坐在草坪上",
        )
        assert len(state.current_project.facts) == 1

        # Step 6: Verify matrix data
        from src.ui.pages.matrix import build_matrix_data
        rows = build_matrix_data(state.current_project)
        assert len(rows) == 1
        emma_row = rows[0]
        assert emma_row["character"] == "Emma"
        assert emma_row["15:00"] == "草坪"
        assert emma_row["15:00_status"] == "confirmed"

    def test_script_analysis_to_deduction_flow(self, state, mock_analysis_result):
        """Test creating deductions from analysis using _create_single_deduction."""
        import src.ui.pages.scripts as scripts_mod

        state.create_project(name="推断测试")
        state.add_character(name="Emma")
        state.add_location(name="草坪")
        state.add_time_slot("15:00")
        script = state.add_script(raw_text="15:00，Emma 坐在草坪上")

        # Patch scripts module's app_state
        original_app_state = scripts_mod.app_state
        scripts_mod.app_state = state
        try:
            proj = state.current_project
            fact_dict = mock_analysis_result["direct_facts"][0]
            success = scripts_mod._create_single_deduction(proj, fact_dict, script.id)
            assert success is True
            assert len(proj.deductions) == 1
            ded = proj.deductions[0]
            assert ded.status == DeductionStatus.pending
            assert ded.confidence == ConfidenceLevel.certain
        finally:
            scripts_mod.app_state = original_app_state

    def test_multiple_scripts_accumulate(self, state):
        """Multiple scripts should have correct source_order."""
        state.create_project(name="多剧本测试")
        s1 = state.add_script(raw_text="第一幕")
        s2 = state.add_script(raw_text="第二幕")
        s3 = state.add_script(raw_text="第三幕")
        assert s1.metadata.source_order == 1
        assert s2.metadata.source_order == 2
        assert s3.metadata.source_order == 3
        assert len(state.current_project.scripts) == 3

    def test_persistence_across_reload(self, state):
        """Data should survive save → load cycle."""
        project = state.create_project(name="持久化测试", time_slots=["10:00"])
        state.add_character(name="TestChar")
        state.add_location(name="TestLoc")
        pid = project.id

        # Reload from disk
        state.current_project = None
        state.load_project(pid)
        assert state.current_project.name == "持久化测试"
        assert len(state.current_project.characters) == 1
        assert state.current_project.characters[0].name == "TestChar"


# ---------------------------------------------------------------------------
# Populated 3×3×3 fixture for deduction / cascade / accept-reject tests
# ---------------------------------------------------------------------------

@pytest.fixture
def populated_state(state):
    """Create a 3×3×3 project: Emma/Alice/Bob × 草坪/图书馆/厨房 × 14:00/15:00/16:00."""
    state.create_project(name="E2E推断测试", time_slots=["14:00", "15:00", "16:00"])
    state.add_character(name="Emma")
    state.add_character(name="Alice")
    state.add_character(name="Bob")
    state.add_location(name="草坪")
    state.add_location(name="图书馆")
    state.add_location(name="厨房")
    return state


class TestCascadeE2E:
    def test_cascade_after_filling_two_of_three(self, populated_state):
        """When 2 of 3 chars are placed at a time, cascade should find the third."""
        s = populated_state
        proj = s.current_project
        emma, alice, bob = proj.characters
        lawn, lib, kitchen = proj.locations

        # Place Emma→草坪 and Alice→图书馆 at 14:00
        s.add_fact(character_id=emma.id, location_id=lawn.id, time_slot="14:00")
        s.add_fact(character_id=alice.id, location_id=lib.id, time_slot="14:00")

        # Cascade should deduce Bob→厨房 at 14:00
        new_deds = DeductionService.run_cascade(proj)
        bob_14 = next(
            (d for d in new_deds if d.character_id == bob.id and d.time_slot == "14:00"),
            None,
        )
        assert bob_14 is not None
        assert bob_14.location_id == kitchen.id
        assert bob_14.confidence == ConfidenceLevel.certain

    def test_cascade_no_result_with_ambiguity(self, populated_state):
        """Only 1 fact at a time slot should NOT trigger cascade (2 remaining)."""
        s = populated_state
        proj = s.current_project
        emma = proj.characters[0]
        lawn = proj.locations[0]

        s.add_fact(character_id=emma.id, location_id=lawn.id, time_slot="14:00")
        new_deds = DeductionService.run_cascade(proj)
        # Alice and Bob both have 2 remaining locations — no cascade
        deds_14 = [d for d in new_deds if d.time_slot == "14:00"]
        assert len(deds_14) == 0


class TestAcceptRejectE2E:
    def test_accept_deduction_creates_fact(self, populated_state):
        """Accepting a deduction should create a corresponding Fact."""
        s = populated_state
        proj = s.current_project
        emma = proj.characters[0]
        lawn = proj.locations[0]

        ded = Deduction(
            character_id=emma.id,
            location_id=lawn.id,
            time_slot="15:00",
            confidence=ConfidenceLevel.high,
            reasoning="测试推断",
        )
        s.add_deduction(ded)
        assert len(s.get_pending_deductions()) == 1

        fact = s.accept_deduction(ded.id)
        assert fact is not None
        assert fact.character_id == emma.id
        assert fact.location_id == lawn.id
        assert fact.time_slot == "15:00"
        assert fact.source_type == SourceType.ai_deduction
        assert len(s.get_pending_deductions()) == 0
        assert ded.status == DeductionStatus.accepted

    def test_reject_deduction_creates_rejection(self, populated_state):
        """Rejecting a deduction should create a Rejection record."""
        s = populated_state
        proj = s.current_project
        emma = proj.characters[0]
        lawn = proj.locations[0]

        ded = Deduction(
            character_id=emma.id,
            location_id=lawn.id,
            time_slot="15:00",
            confidence=ConfidenceLevel.medium,
            reasoning="可疑推断",
        )
        s.add_deduction(ded)
        rejection = s.reject_deduction(ded.id, reason="证据不足")
        assert rejection is not None
        assert rejection.character_id == emma.id
        assert rejection.reason == "证据不足"
        assert ded.status == DeductionStatus.rejected
        assert len(proj.rejections) == 1

    def test_accept_then_cascade(self, populated_state):
        """Accepting a deduction should enable cascade to find new deductions."""
        s = populated_state
        proj = s.current_project
        emma, alice, bob = proj.characters
        lawn, lib, kitchen = proj.locations

        # Place Emma→草坪 at 14:00 as fact
        s.add_fact(character_id=emma.id, location_id=lawn.id, time_slot="14:00")

        # Create and accept deduction: Alice→图书馆 at 14:00
        ded = Deduction(
            character_id=alice.id,
            location_id=lib.id,
            time_slot="14:00",
            confidence=ConfidenceLevel.high,
            reasoning="AI推断",
        )
        s.add_deduction(ded)
        fact = s.accept_deduction(ded.id)
        assert fact is not None

        # Now cascade: Bob must be in 厨房 at 14:00
        cascade_deds = DeductionService.run_cascade(proj)
        bob_14 = next(
            (d for d in cascade_deds if d.character_id == bob.id and d.time_slot == "14:00"),
            None,
        )
        assert bob_14 is not None
        assert bob_14.location_id == kitchen.id


# ---------------------------------------------------------------------------
# Entity management CRUD E2E tests
# ---------------------------------------------------------------------------


class TestCharacterCRUDE2E:
    def test_character_full_lifecycle(self, state):
        """Test add → update (name, aliases, status) → remove character."""
        state.create_project(name="人物CRUD测试")

        # Create
        char = state.add_character(
            name="Emma",
            aliases=["艾玛"],
            description="主角",
            status=CharacterStatus.confirmed,
        )
        assert char.name == "Emma"
        assert char.aliases == ["艾玛"]
        assert char.status == CharacterStatus.confirmed

        # Update
        updated = state.update_character(
            char.id,
            name="Emma Updated",
            aliases=["艾玛", "Em"],
            status=CharacterStatus.suspected,
        )
        assert updated.name == "Emma Updated"
        assert len(updated.aliases) == 2
        assert updated.status == CharacterStatus.suspected

        # Verify persistence
        loaded = state.store.load_project(state.current_project.id)
        assert loaded.characters[0].name == "Emma Updated"

        # Remove
        removed = state.remove_character(char.id)
        assert removed is True
        assert len(state.current_project.characters) == 0


class TestLocationCRUDE2E:
    def test_location_full_lifecycle(self, state):
        """Test add → update (name, aliases) → remove location."""
        state.create_project(name="地点CRUD测试")

        loc = state.add_location(name="草坪", aliases=["Lawn"], description="户外")
        assert loc.name == "草坪"

        updated = state.update_location(loc.id, name="大草坪", aliases=["Lawn", "草地"])
        assert updated.name == "大草坪"
        assert len(updated.aliases) == 2

        removed = state.remove_location(loc.id)
        assert removed is True
        assert len(state.current_project.locations) == 0


class TestTimeSlotE2E:
    def test_time_slot_add_sort_remove(self, state):
        """Time slots should auto-sort and prevent duplicates."""
        state.create_project(name="时间测试")

        state.add_time_slot("16:00")
        state.add_time_slot("14:00")
        state.add_time_slot("15:00")
        assert state.current_project.time_slots == ["14:00", "15:00", "16:00"]

        # Duplicate
        added = state.add_time_slot("14:00")
        assert added is False

        # Invalid format
        with pytest.raises(ValueError, match="HH:MM"):
            state.add_time_slot("9am")

        # Remove
        state.remove_time_slot("15:00")
        assert state.current_project.time_slots == ["14:00", "16:00"]


class TestHintE2E:
    def test_hint_add_and_remove(self, state):
        """Test hint/rule management."""
        state.create_project(name="规则测试")

        hint = state.add_hint(hint_type=HintType.rule, content="每人每时段只能在一个地点")
        assert hint.type == HintType.rule
        assert hint.content == "每人每时段只能在一个地点"

        hint2 = state.add_hint(hint_type=HintType.hint, content="注意厨房的线索")
        assert len(state.current_project.hints) == 2

        state.remove_hint(hint.id)
        assert len(state.current_project.hints) == 1
        assert state.current_project.hints[0].id == hint2.id


class TestManualFactE2E:
    def test_manual_fact_entry_and_deletion(self, state):
        """Test adding and removing facts manually."""
        state.create_project(name="事实测试", time_slots=["14:00", "15:00"])
        char = state.add_character(name="Emma")
        loc = state.add_location(name="草坪")

        fact = state.add_fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot="14:00",
            source_type=SourceType.user_input,
            source_evidence="手动观察",
        )
        assert fact.source_type == SourceType.user_input
        assert fact.source_evidence == "手动观察"
        assert len(state.current_project.facts) == 1

        # Verify in matrix
        from src.ui.pages.matrix import build_matrix_data
        rows = build_matrix_data(state.current_project)
        assert rows[0]["14:00"] == "草坪"
        assert rows[0]["14:00_status"] == "confirmed"

        # Delete
        removed = state.remove_fact(fact.id)
        assert removed is True
        assert len(state.current_project.facts) == 0

        # Matrix should now be empty
        rows = build_matrix_data(state.current_project)
        assert rows[0]["14:00"] == ""
        assert rows[0]["14:00_status"] == "unknown"
