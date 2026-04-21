from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.models.puzzle import (
    Character,
    ConfidenceLevel,
    Deduction,
    Fact,
    Location,
    Project,
    Script,
    SourceType,
    TimeSlot,
)
from src.storage.sqlite_store import SQLiteStore
from src.ui.state import AppState

LIST_PROJECT_THRESHOLD_SECONDS = 0.25
LOAD_PROJECT_THRESHOLD_SECONDS = 0.2
WRITE_PATH_THRESHOLD_SECONDS = 0.12
SEEDED_PROJECT_COUNT = 120


def _seed_project(index: int) -> Project:
    time_slots = [
        TimeSlot(id=f"ts-{index}-{slot}", label=f"{9 + slot:02d}:00", sort_order=slot)
        for slot in range(4)
    ]
    characters = [
        Character(id=f"char-{index}-{char}", name=f"角色{index}-{char}") for char in range(8)
    ]
    locations = [
        Location(id=f"loc-{index}-{loc}", name=f"地点{index}-{loc}") for loc in range(6)
    ]
    project = Project(
        id=f"project-{index}",
        name=f"项目 {index:03d}",
        description="performance smoke",
        time_slots=time_slots,
        characters=characters,
        locations=locations,
    )
    project.scripts = [
        Script(id=f"script-{index}-{script}", title=f"剧本 {script}", raw_text="线索文本")
        for script in range(3)
    ]
    for fact_index, character in enumerate(characters[:4]):
        project.facts.append(
            Fact(
                id=f"fact-{index}-{fact_index}",
                character_id=character.id,
                location_id=locations[fact_index % len(locations)].id,
                time_slot=time_slots[fact_index % len(time_slots)].id,
                source_type=SourceType.user_input,
                source_script_ids=[project.scripts[0].id],
            )
        )
    for ded_index, character in enumerate(characters[4:7], start=1):
        project.deductions.append(
            Deduction(
                id=f"ded-{index}-{ded_index}",
                character_id=character.id,
                location_id=locations[ded_index % len(locations)].id,
                time_slot=time_slots[ded_index % len(time_slots)].id,
                confidence=ConfidenceLevel.medium,
                reasoning="smoke pending",
                supporting_script_ids=[project.scripts[1].id],
            )
        )
    return project


@pytest.fixture
def seeded_sqlite_state(tmp_path: Path) -> AppState:
    store = SQLiteStore(db_path=tmp_path / "performance.db")
    for index in range(SEEDED_PROJECT_COUNT):
        store.save_project(_seed_project(index))
    return AppState(store=store)


def test_project_list_performance_smoke(seeded_sqlite_state: AppState) -> None:
    start = time.perf_counter()
    summaries = seeded_sqlite_state.list_projects()
    elapsed = time.perf_counter() - start

    assert len(summaries) == SEEDED_PROJECT_COUNT
    assert elapsed < LIST_PROJECT_THRESHOLD_SECONDS


def test_project_load_performance_smoke(seeded_sqlite_state: AppState) -> None:
    target = seeded_sqlite_state.list_projects()[SEEDED_PROJECT_COUNT // 2]

    start = time.perf_counter()
    seeded_sqlite_state.load_project(target.id)
    elapsed = time.perf_counter() - start

    assert seeded_sqlite_state.current_project is not None
    assert seeded_sqlite_state.current_project.id == target.id
    assert len(seeded_sqlite_state.current_project.characters) == 8
    assert elapsed < LOAD_PROJECT_THRESHOLD_SECONDS


def test_core_write_path_performance_smoke(seeded_sqlite_state: AppState) -> None:
    target = seeded_sqlite_state.list_projects()[0]
    seeded_sqlite_state.load_project(target.id)
    project = seeded_sqlite_state.current_project
    assert project is not None

    new_character = seeded_sqlite_state.add_character("性能角色")
    new_location = seeded_sqlite_state.add_location("性能地点")
    time_slot_id = project.time_slots[0].id
    pending = Deduction(
        character_id=new_character.id,
        location_id=new_location.id,
        time_slot=time_slot_id,
        confidence=ConfidenceLevel.high,
        reasoning="write smoke",
    )
    assert seeded_sqlite_state.add_deduction(pending) is True

    start = time.perf_counter()
    fact = seeded_sqlite_state.accept_deduction(pending.id)
    elapsed = time.perf_counter() - start

    assert fact is not None
    assert fact.character_id == new_character.id
    assert elapsed < WRITE_PATH_THRESHOLD_SECONDS
