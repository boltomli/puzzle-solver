import sqlite3

import pytest

from src.models.puzzle import (
    Character,
    ConfidenceLevel,
    Deduction,
    Fact,
    Location,
    Script,
    ScriptMetadata,
    SourceType,
    TimeSlot,
)
from src.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(db_path=tmp_path / "projects.db")


def test_create_schema_creates_core_tables(store):
    store.create_schema()

    with sqlite3.connect(store.db_path) as conn:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

    assert {
        "projects",
        "characters",
        "locations",
        "time_slots",
        "scripts",
        "facts",
        "deductions",
        "rejections",
    }.issubset(names)


def test_create_and_list_projects_returns_summary_counts(store):
    project = store.create_project(name="案件A", description="测试")
    project.characters.append(Character(name="Alice"))
    project.locations.append(Location(name="Library"))
    project.time_slots.append(TimeSlot(label="09:00"))
    project.scripts.append(
        Script(title="Scene 1", raw_text="text", metadata=ScriptMetadata(source_order=1))
    )
    project.facts.append(
        Fact(
            character_id=project.characters[0].id,
            location_id=project.locations[0].id,
            time_slot=project.time_slots[0].id,
            source_type=SourceType.user_input,
        )
    )
    project.updated_at = project.updated_at
    store.save_project(project)

    summaries = store.list_projects()

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.id == project.id
    assert summary.name == "案件A"
    assert summary.character_count == 1
    assert summary.location_count == 1
    assert summary.script_count == 1
    assert summary.fact_count == 1


def test_save_and_load_preserves_core_chain_ids_and_payloads(store):
    project = store.create_project(name="Chain")
    character = Character(name="Alice", aliases=["A"])
    location = Location(name="Library", aliases=["Lib"])
    time_slot = TimeSlot(label="09:00", description="Morning", sort_order=2)
    script = Script(
        title="Scene 1",
        raw_text="Alice entered the library",
        metadata=ScriptMetadata(
            stated_time="09:00",
            stated_location="Library",
            characters_mentioned=["Alice"],
            source_order=1,
            user_notes="note",
        ),
        analysis_result={"characters_mentioned": ["Alice"]},
    )
    project.characters.append(character)
    project.locations.append(location)
    project.time_slots.append(time_slot)
    project.scripts.append(script)
    fact = Fact(
        character_id=character.id,
        location_id=location.id,
        time_slot=time_slot.id,
        source_type=SourceType.user_input,
        source_evidence="seen",
        source_script_ids=[script.id],
    )
    deduction = Deduction(
        character_id=character.id,
        location_id=location.id,
        time_slot=time_slot.id,
        confidence=ConfidenceLevel.high,
        reasoning="likely",
        supporting_script_ids=[script.id],
        depends_on_fact_ids=[fact.id],
    )
    project.facts.append(fact)
    project.deductions.append(deduction)
    store.save_project(project)

    loaded = store.load_project(project.id)

    assert loaded.id == project.id
    assert loaded.characters[0].id == character.id
    assert loaded.characters[0].aliases == ["A"]
    assert loaded.locations[0].id == location.id
    assert loaded.time_slots[0].id == time_slot.id
    assert loaded.time_slots[0].description == "Morning"
    assert loaded.scripts[0].id == script.id
    assert loaded.scripts[0].metadata.characters_mentioned == ["Alice"]
    assert loaded.scripts[0].analysis_result == {"characters_mentioned": ["Alice"]}
    assert loaded.facts[0].source_script_ids == [script.id]
    assert loaded.deductions[0].supporting_script_ids == [script.id]
    assert loaded.deductions[0].depends_on_fact_ids == [fact.id]


def test_delete_project_removes_it_from_storage(store):
    project = store.create_project(name="To delete")

    store.delete_project(project.id)

    with pytest.raises(FileNotFoundError):
        store.load_project(project.id)
