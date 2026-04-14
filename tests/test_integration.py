"""Cross-area integration tests — VAL-CROSS-001 through VAL-CROSS-008.

Each test exercises the full stack: AppState → JsonRepository → CacheManager → JsonStore (disk).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from src.models.puzzle import (
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    HintType,
    SourceType,
)
from src.services.prompt_engine import PromptEngine
from src.storage.json_store import JsonStore
from src.ui.pages.matrix import build_matrix_data
from src.ui.state import AppState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    temp_dir = tempfile.mkdtemp(prefix="puzzle_integration_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def state(temp_data_dir):
    """Create an AppState with a temporary data directory."""
    store = JsonStore(data_dir=temp_data_dir)
    return AppState(store=store)


def _fresh_state(data_dir: Path) -> AppState:
    """Create a brand-new AppState pointing at the same data directory.

    This simulates a cold reload: new JsonStore, new CacheManager, indexes
    rebuilt from disk.
    """
    store = JsonStore(data_dir=data_dir)
    return AppState(store=store)


# ---------------------------------------------------------------------------
# VAL-CROSS-001: Add entity → index reflects → matrix shows new row/column
# ---------------------------------------------------------------------------


class TestCross001AddEntityIndexMatrix:
    """Adding an entity populates indexes instantly and shows in matrix output."""

    def test_add_character_index_and_matrix_row(self, state: AppState):
        """Add a character → char_by_id/char_by_name populated → matrix has new row."""
        state.create_project(name="CROSS-001")
        ts = state.add_time_slot("10:00")

        char = state.add_character(name="Alice")

        # Index reflects immediately
        assert state.cache.char_by_id[char.id] is char
        assert state.cache.char_by_name["alice"] is char

        # Matrix includes a new row with unknown cells
        rows = build_matrix_data(state.current_project)
        assert len(rows) == 1
        assert rows[0]["character"] == "Alice"
        assert rows[0][ts.id] == ""
        assert rows[0][f"{ts.id}_status"] == "unknown"

    def test_add_location_index(self, state: AppState):
        """Add a location → loc_by_id/loc_by_name populated."""
        state.create_project(name="CROSS-001-loc")

        loc = state.add_location(name="Library")

        assert state.cache.loc_by_id[loc.id] is loc
        assert state.cache.loc_by_name["library"] is loc

    def test_add_time_slot_matrix_column(self, state: AppState):
        """Add a time slot → ts_by_id populated → matrix has new column."""
        state.create_project(name="CROSS-001-ts")
        state.add_character(name="Bob")

        ts = state.add_time_slot("14:00")

        assert state.cache.ts_by_id[ts.id] is ts
        assert ts.label in state.cache.ts_label_map

        rows = build_matrix_data(state.current_project)
        assert len(rows) == 1
        # The row must have a key for the new time slot
        assert ts.id in rows[0]
        assert rows[0][f"{ts.id}_status"] == "unknown"


# ---------------------------------------------------------------------------
# VAL-CROSS-002: Cascade delete → indexes cleaned → matrix adjusted → JSON consistent
# ---------------------------------------------------------------------------


class TestCross002CascadeDeleteIndexMatrix:
    """Removing a character with references cascades, cleans indexes, adjusts matrix,
    and persists cleanly."""

    def test_cascade_delete_full_flow(self, state: AppState, temp_data_dir: Path):
        """Remove character with fact/deduction/rejection → indexes clean → matrix
        removes row → reload from disk identical."""
        state.create_project(name="CROSS-002")
        ts = state.add_time_slot("12:00")
        char_a = state.add_character(name="CharA")
        state.add_character(name="CharB")
        loc = state.add_location(name="Park")

        # Create fact for CharA
        state.add_fact(char_a.id, loc.id, ts.id, source_type=SourceType.user_input)

        # Create pending deduction for CharA (different triple needed – use a second ts)
        ts2 = state.add_time_slot("13:00")
        ded = Deduction(
            character_id=char_a.id,
            location_id=loc.id,
            time_slot=ts2.id,
            confidence=ConfidenceLevel.high,
            reasoning="test",
        )
        state.add_deduction(ded)

        # Create rejection for CharA at yet another time slot
        ts3 = state.add_time_slot("14:00")
        ded_rej = Deduction(
            character_id=char_a.id,
            location_id=loc.id,
            time_slot=ts3.id,
            confidence=ConfidenceLevel.medium,
            reasoning="test rej",
        )
        state.add_deduction(ded_rej)
        state.reject_deduction(ded_rej.id, reason="wrong")

        # Verify indexes before delete
        assert (char_a.id, loc.id, ts.id) in state._fact_index
        assert (char_a.id, loc.id, ts2.id) in state._pending_index
        assert (char_a.id, loc.id, ts3.id) in state._rejection_index

        # Delete CharA
        removed = state.remove_character(char_a.id)
        assert removed is True

        # Indexes cleaned
        assert (char_a.id, loc.id, ts.id) not in state._fact_index
        assert (char_a.id, loc.id, ts2.id) not in state._pending_index
        assert (char_a.id, loc.id, ts3.id) not in state._rejection_index
        assert char_a.id not in state.cache.char_by_id

        # Matrix has only CharB
        rows = build_matrix_data(state.current_project)
        assert len(rows) == 1
        assert rows[0]["character"] == "CharB"

        # Persistence: reload from disk and compare
        proj_id = state.current_project.id
        state2 = _fresh_state(temp_data_dir)
        state2.load_project(proj_id)
        assert len(state2.current_project.characters) == 1
        assert state2.current_project.characters[0].name == "CharB"
        assert len(state2.current_project.facts) == 0
        # Dedup indexes rebuilt correctly
        assert len(state2._fact_index) == 0
        assert len(state2._pending_index) == 0
        # Rejection for charA was cascade-deleted
        assert len(state2.current_project.rejections) == 0


# ---------------------------------------------------------------------------
# VAL-CROSS-003: Full deduction lifecycle end-to-end
# ---------------------------------------------------------------------------


class TestCross003DeductionLifecycle:
    """add_deduction → pending_index → matrix pending → accept → fact_index → matrix confirmed."""

    def test_full_deduction_lifecycle(self, state: AppState):
        state.create_project(name="CROSS-003")
        ts = state.add_time_slot("09:00")
        char = state.add_character(name="Eve")
        loc = state.add_location(name="Garden")

        # --- Stage 1: add_deduction → pending ---
        ded = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.high,
            reasoning="Seen in garden",
        )
        added = state.add_deduction(ded)
        assert added is True
        assert (char.id, loc.id, ts.id) in state._pending_index

        # Matrix shows pending
        rows = build_matrix_data(state.current_project)
        cell_val = rows[0][ts.id]
        cell_status = rows[0][f"{ts.id}_status"]
        assert cell_val == "(Garden)"
        assert cell_status == "pending"

        # --- Stage 2: accept → fact ---
        fact = state.accept_deduction(ded.id)
        assert fact is not None
        assert fact.source_type == SourceType.ai_deduction
        assert fact.from_deduction_id == ded.id

        # Triple moved from pending to fact index
        assert (char.id, loc.id, ts.id) not in state._pending_index
        assert (char.id, loc.id, ts.id) in state._fact_index

        # Matrix shows confirmed
        rows = build_matrix_data(state.current_project)
        assert rows[0][ts.id] == "Garden"
        assert rows[0][f"{ts.id}_status"] == "confirmed"

        # Prompt includes confirmed fact
        engine = PromptEngine()
        _, user_prompt = engine.build_deduction_prompt(state.current_project)
        assert "Eve" in user_prompt
        assert "Garden" in user_prompt
        assert "✅" in user_prompt


# ---------------------------------------------------------------------------
# VAL-CROSS-004: Save-reload round trip preserves all data and indexes
# ---------------------------------------------------------------------------


class TestCross004SaveReloadRoundTrip:
    """Create project with all entity types, save, reload, compare field-by-field."""

    def test_round_trip_preserves_everything(self, state: AppState, temp_data_dir: Path):
        state.create_project(name="CROSS-004-RT")
        proj = state.current_project

        # Characters
        c1 = state.add_character(name="Alpha", aliases=["A"], description="Leader")
        c2 = state.add_character(name="Beta")

        # Locations
        l1 = state.add_location(name="Room1", aliases=["R1"])
        l2 = state.add_location(name="Room2")

        # Time slots
        t1 = state.add_time_slot("08:00", description="Morning")
        t2 = state.add_time_slot("12:00")

        # Hints
        state.add_hint(HintType.rule, "No two chars in same room")

        # Script
        sc = state.add_script(raw_text="Alpha was in Room1 at 08:00", title="Script#1")
        state.save_script_analysis(sc.id, {"characters_mentioned": [{"name": "Alpha"}]})

        # Facts
        state.add_fact(c1.id, l1.id, t1.id, source_type=SourceType.user_input)

        # Deduction (pending)
        ded = Deduction(
            character_id=c2.id,
            location_id=l2.id,
            time_slot=t2.id,
            confidence=ConfidenceLevel.medium,
            reasoning="Elimination",
        )
        state.add_deduction(ded)

        # Capture snapshot of dedup indexes
        fact_index_before = set(state._fact_index)
        pending_index_before = set(state._pending_index)
        rejection_index_before = set(state._rejection_index)

        # Matrix snapshot
        matrix_before = build_matrix_data(state.current_project)

        # --- Reload into fresh AppState ---
        state2 = _fresh_state(temp_data_dir)
        state2.load_project(proj.id)
        proj2 = state2.current_project

        # Characters
        assert len(proj2.characters) == 2
        c1_r = next(c for c in proj2.characters if c.id == c1.id)
        assert c1_r.name == "Alpha"
        assert c1_r.aliases == ["A"]
        assert c1_r.description == "Leader"

        # Locations
        assert len(proj2.locations) == 2
        l1_r = next(lo for lo in proj2.locations if lo.id == l1.id)
        assert l1_r.aliases == ["R1"]

        # Time slots
        assert len(proj2.time_slots) == 2
        t1_r = next(ts for ts in proj2.time_slots if ts.id == t1.id)
        assert t1_r.label == "08:00"
        assert t1_r.description == "Morning"

        # Hints
        assert len(proj2.hints) == 1
        assert proj2.hints[0].content == "No two chars in same room"

        # Scripts + analysis
        assert len(proj2.scripts) == 1
        assert proj2.scripts[0].analysis_result is not None
        assert proj2.scripts[0].analysis_result["characters_mentioned"][0]["name"] == "Alpha"

        # Facts
        assert len(proj2.facts) == 1
        assert proj2.facts[0].character_id == c1.id

        # Deductions
        assert len(proj2.deductions) == 1
        assert proj2.deductions[0].status == DeductionStatus.pending

        # Dedup indexes rebuilt identically
        assert set(state2._fact_index) == fact_index_before
        assert set(state2._pending_index) == pending_index_before
        assert set(state2._rejection_index) == rejection_index_before

        # Matrix identical
        matrix_after = build_matrix_data(proj2)
        assert matrix_after == matrix_before


# ---------------------------------------------------------------------------
# VAL-CROSS-005: Rejection lifecycle blocks re-suggestion
# ---------------------------------------------------------------------------


class TestCross005RejectionLifecycle:
    """Reject → rejection_index → add_deduction same triple returns False → prompt
    includes rejection."""

    def test_rejection_blocks_and_appears_in_prompt(self, state: AppState):
        state.create_project(name="CROSS-005")
        ts = state.add_time_slot("16:00")
        char = state.add_character(name="Villain")
        loc = state.add_location(name="Cellar")

        # Add and reject a deduction
        ded = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.low,
            reasoning="Weak evidence",
        )
        state.add_deduction(ded)
        rej = state.reject_deduction(ded.id, reason="Contradicts witness")
        assert rej is not None

        # rejection_index has the triple
        assert (char.id, loc.id, ts.id) in state._rejection_index

        # Re-adding the same triple returns False
        ded2 = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.high,
            reasoning="New evidence",
        )
        assert state.add_deduction(ded2) is False

        # Prompt includes the rejection in REJECTED section
        engine = PromptEngine()
        _, user_prompt = engine.build_deduction_prompt(state.current_project)
        assert "REJECTED" in user_prompt
        assert "Villain" in user_prompt
        assert "Cellar" in user_prompt
        assert "Contradicts witness" in user_prompt

        # Matrix still shows cell as unknown (no confirmed fact, no pending)
        rows = build_matrix_data(state.current_project)
        assert rows[0][ts.id] == ""
        assert rows[0][f"{ts.id}_status"] == "unknown"


# ---------------------------------------------------------------------------
# VAL-CROSS-006: Script analysis → entity creation → deduction → accept → matrix confirmed
# ---------------------------------------------------------------------------


class TestCross006ScriptAnalysisPipeline:
    """Full ingestion pipeline: add script → save analysis → create deductions →
    accept → matrix confirmed → analysis survives reload."""

    def test_script_to_confirmed_matrix(self, state: AppState, temp_data_dir: Path):
        state.create_project(name="CROSS-006")

        # Add base entities
        char = state.add_character(name="Emma")
        loc = state.add_location(name="草坪")
        state.add_time_slot("15:00")

        # Add script and save analysis
        script = state.add_script(raw_text="15:00，Emma 坐在草坪上", title="剧本#1")
        analysis = {
            "characters_mentioned": [
                {"character_id": char.id, "name": "Emma", "is_new": False, "context": "坐在草坪上"},
            ],
            "locations_mentioned": [
                {"location_id": loc.id, "name": "草坪", "is_new": False, "context": "Emma坐在此处"},
            ],
            "time_references": [
                {"time_slot": "15:00", "reference_text": "15:00", "is_explicit": True},
            ],
            "direct_facts": [
                {
                    "character_name": "Emma",
                    "location_name": "草坪",
                    "time_slot": "15:00",
                    "confidence": "certain",
                    "evidence": "15:00，Emma 坐在草坪上",
                },
            ],
            "alias_candidates": [],
        }
        state.save_script_analysis(script.id, analysis)

        # Create deduction from direct_facts (simulating _create_deductions_from_facts)
        ts_id = state.cache.ts_label_map.get("15:00")
        assert ts_id is not None

        ded = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts_id,
            confidence=ConfidenceLevel.certain,
            reasoning="剧本分析：Emma 在 15:00 位于 草坪",
            supporting_script_ids=[script.id],
        )
        added = state.add_deduction(ded)
        assert added is True

        # Accept deduction
        fact = state.accept_deduction(ded.id)
        assert fact is not None

        # Matrix shows confirmed
        rows = build_matrix_data(state.current_project)
        assert rows[0][ts_id] == "草坪"
        assert rows[0][f"{ts_id}_status"] == "confirmed"

        # Reload and verify analysis survives
        proj_id = state.current_project.id
        state2 = _fresh_state(temp_data_dir)
        state2.load_project(proj_id)
        reloaded_script = state2.current_project.scripts[0]
        assert reloaded_script.analysis_result is not None
        assert reloaded_script.analysis_result["direct_facts"][0]["character_name"] == "Emma"

        # Matrix still confirmed after reload
        rows2 = build_matrix_data(state2.current_project)
        assert rows2[0][ts_id] == "草坪"
        assert rows2[0][f"{ts_id}_status"] == "confirmed"


# ---------------------------------------------------------------------------
# VAL-CROSS-007: Entity merge → alias in lookups → prompts include alias
# ---------------------------------------------------------------------------


class TestCross007EntityMerge:
    """merge_character adds alias → prompt includes alias → no entity duplication."""

    def test_merge_character_alias_in_prompt(self, state: AppState):
        state.create_project(name="CROSS-007")
        state.add_time_slot("11:00")
        char = state.add_character(name="Zhang San")
        state.add_location(name="Office")

        # Merge alias
        merged = state.merge_character("张三", char.id)
        assert merged is not None
        assert "张三" in merged.aliases

        # Character count unchanged (no duplication)
        assert len(state.current_project.characters) == 1

        # Prompt includes "also known as" listing
        engine = PromptEngine()
        _, user_prompt = engine.build_deduction_prompt(state.current_project)
        assert "Zhang San" in user_prompt
        assert "张三" in user_prompt
        assert "also known as" in user_prompt

    def test_merge_location_alias_in_prompt(self, state: AppState):
        state.create_project(name="CROSS-007-loc")
        loc = state.add_location(name="Library")
        state.add_time_slot("10:00")

        merged = state.merge_location("图书馆", loc.id)
        assert merged is not None
        assert "图书馆" in merged.aliases
        assert len(state.current_project.locations) == 1

        engine = PromptEngine()
        _, user_prompt = engine.build_deduction_prompt(state.current_project)
        assert "Library" in user_prompt
        assert "图书馆" in user_prompt
        assert "also known as" in user_prompt


# ---------------------------------------------------------------------------
# VAL-CROSS-008: Three-way dedup guard across all states
# ---------------------------------------------------------------------------


class TestCross008ThreeWayDedup:
    """A triple in fact_index, pending_index, or rejection_index blocks add_deduction."""

    def test_fact_blocks_deduction(self, state: AppState):
        """Triple in fact_index → add_deduction returns False."""
        state.create_project(name="CROSS-008-fact")
        ts = state.add_time_slot("08:00")
        char = state.add_character(name="C1")
        loc = state.add_location(name="L1")

        state.add_fact(char.id, loc.id, ts.id)

        ded = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.high,
            reasoning="Should be blocked",
        )
        assert state.add_deduction(ded) is False

    def test_pending_blocks_deduction(self, state: AppState):
        """Triple in pending_index → add_deduction returns False."""
        state.create_project(name="CROSS-008-pending")
        ts = state.add_time_slot("09:00")
        char = state.add_character(name="C2")
        loc = state.add_location(name="L2")

        ded1 = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.medium,
            reasoning="First",
        )
        assert state.add_deduction(ded1) is True

        ded2 = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.high,
            reasoning="Duplicate",
        )
        assert state.add_deduction(ded2) is False

    def test_rejection_blocks_deduction(self, state: AppState):
        """Triple in rejection_index → add_deduction returns False."""
        state.create_project(name="CROSS-008-rejection")
        ts = state.add_time_slot("10:00")
        char = state.add_character(name="C3")
        loc = state.add_location(name="L3")

        ded = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.low,
            reasoning="Will be rejected",
        )
        state.add_deduction(ded)
        state.reject_deduction(ded.id)

        ded2 = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts.id,
            confidence=ConfidenceLevel.certain,
            reasoning="Should be blocked by rejection",
        )
        assert state.add_deduction(ded2) is False

    def test_all_transitions_no_duplicates(self, state: AppState):
        """Walk through all dedup transitions: fact, pending, accept, reject — no
        duplicate records at any point."""
        state.create_project(name="CROSS-008-all")
        ts1 = state.add_time_slot("07:00")
        ts2 = state.add_time_slot("08:00")
        ts3 = state.add_time_slot("09:00")
        char = state.add_character(name="CAll")
        loc = state.add_location(name="LAll")

        # Triple 1: add fact directly → blocks deduction
        state.add_fact(char.id, loc.id, ts1.id)
        ded1 = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts1.id,
            confidence=ConfidenceLevel.high,
            reasoning="blocked by fact",
        )
        assert state.add_deduction(ded1) is False

        # Triple 2: add deduction → accept → now in fact_index → blocks new deduction
        ded2 = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts2.id,
            confidence=ConfidenceLevel.high,
            reasoning="will be accepted",
        )
        assert state.add_deduction(ded2) is True
        state.accept_deduction(ded2.id)
        ded2_dup = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts2.id,
            confidence=ConfidenceLevel.medium,
            reasoning="blocked by accepted fact",
        )
        assert state.add_deduction(ded2_dup) is False

        # Triple 3: add deduction → reject → now in rejection_index → blocks
        ded3 = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts3.id,
            confidence=ConfidenceLevel.medium,
            reasoning="will be rejected",
        )
        assert state.add_deduction(ded3) is True
        state.reject_deduction(ded3.id)
        ded3_dup = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts3.id,
            confidence=ConfidenceLevel.high,
            reasoning="blocked by rejection",
        )
        assert state.add_deduction(ded3_dup) is False

        # Final: no duplicate records in any list
        proj = state.current_project
        # 2 facts total (1 direct + 1 from accepted deduction)
        assert len(proj.facts) == 2
        # 3 deductions (1 accepted, 1 rejected, and the first ded1 was never added)
        assert len(proj.deductions) == 2
        # 1 rejection
        assert len(proj.rejections) == 1
