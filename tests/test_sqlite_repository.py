import pytest

from src.models.puzzle import CharacterStatus, ConfidenceLevel, Deduction, EntityKind, HintType
from src.storage.sqlite_repository import SQLiteRepository
from src.storage.sqlite_store import SQLiteStore
from src.ui.state import AppState


@pytest.fixture
def sqlite_repo(tmp_path):
    return SQLiteRepository(store=SQLiteStore(db_path=tmp_path / "projects.db"))


@pytest.fixture
def sqlite_repo_with_project(sqlite_repo):
    sqlite_repo.create_project("案件A", "描述", ["09:00", "10:00"])
    return sqlite_repo


@pytest.fixture
def sqlite_state(tmp_path):
    return AppState(store=SQLiteStore(db_path=tmp_path / "state.db"))


def _make_deduction(
    char_id: str,
    loc_id: str,
    ts_id: str,
    *,
    supporting_script_ids: list[str] | None = None,
) -> Deduction:
    return Deduction(
        character_id=char_id,
        location_id=loc_id,
        time_slot=ts_id,
        confidence=ConfidenceLevel.high,
        reasoning="Test reasoning",
        supporting_script_ids=supporting_script_ids or [],
    )


def test_create_project_immediately_usable(sqlite_repo):
    project = sqlite_repo.create_project("立即可用", time_slots=["09:00"])

    char = sqlite_repo.add_character("Alice")
    loc = sqlite_repo.add_location("Library")
    fact = sqlite_repo.add_fact(char.id, loc.id, project.time_slots[0].id)

    assert sqlite_repo.current_project is not None
    assert sqlite_repo.current_project.id == project.id
    assert len(sqlite_repo.current_project.characters) == 1
    assert fact.character_id == char.id


def test_list_projects_empty_and_multiple(sqlite_repo):
    assert sqlite_repo.list_projects() == []

    sqlite_repo.create_project("A")
    sqlite_repo.store.create_project("B")

    summaries = sqlite_repo.list_projects()
    names = {summary.name for summary in summaries}
    assert names == {"A", "B"}


def test_load_project_restores_complete_state(sqlite_repo_with_project):
    char = sqlite_repo_with_project.add_character("Alice")
    loc = sqlite_repo_with_project.add_location("Library")
    script = sqlite_repo_with_project.add_script("text", title="Scene 1", user_notes="note")
    fact = sqlite_repo_with_project.add_fact(
        char.id,
        loc.id,
        sqlite_repo_with_project.current_project.time_slots[0].id,
        source_script_ids=[script.id],
    )
    hint = sqlite_repo_with_project.add_hint(HintType.rule, "Only one person")
    ignored = sqlite_repo_with_project.ignore_entity(EntityKind.character, "Ghost")
    project_id = sqlite_repo_with_project.current_project.id

    sqlite_repo_with_project.current_project = None
    sqlite_repo_with_project.load_project(project_id)
    loaded = sqlite_repo_with_project.current_project

    assert loaded is not None
    assert loaded.characters[0].id == char.id
    assert loaded.locations[0].id == loc.id
    assert loaded.scripts[0].id == script.id
    assert loaded.facts[0].id == fact.id
    assert loaded.hints[0].id == hint.id
    assert loaded.ignored_entities[0].id == ignored.id


def test_save_persists_updates_across_reload(sqlite_repo_with_project):
    char = sqlite_repo_with_project.add_character("Alice")
    sqlite_repo_with_project.update_character(char.id, name="Alice Updated")
    project_id = sqlite_repo_with_project.current_project.id

    sqlite_repo_with_project.current_project = None
    sqlite_repo_with_project.load_project(project_id)

    assert sqlite_repo_with_project.current_project.characters[0].name == "Alice Updated"


@pytest.mark.parametrize(
    "operation,args",
    [
        ("add_character", ("Alice",)),
        ("add_location", ("Library",)),
        ("add_script", ("text",)),
        ("add_fact", ("c", "l", "t")),
        ("add_time_slot", ("09:00",)),
        ("add_hint", (HintType.hint, "content")),
        ("ignore_entity", (EntityKind.character, "Alice")),
        ("merge_character", ("Alice", "target")),
        ("merge_location", ("Library", "target")),
    ],
)
def test_no_project_loaded_failures_are_safe(sqlite_repo, operation, args):
    with pytest.raises(ValueError, match="No project loaded"):
        getattr(sqlite_repo, operation)(*args)


def test_character_location_script_fact_time_slot_hint_and_ignored_entity_parity(
    sqlite_repo_with_project,
):
    char = sqlite_repo_with_project.add_character(
        "Alice", aliases=["A"], description="desc", status=CharacterStatus.suspected
    )
    loc = sqlite_repo_with_project.add_location("Library", aliases=["L"], description="quiet")
    script = sqlite_repo_with_project.add_script("raw", title="Scene", user_notes="memo")
    updated_script = sqlite_repo_with_project.update_script(
        script.id, title="Scene 2", raw_text="raw2", user_notes="memo2"
    )
    fact = sqlite_repo_with_project.add_fact(
        char.id,
        loc.id,
        sqlite_repo_with_project.current_project.time_slots[0].id,
        source_script_ids=[script.id],
    )
    duplicate_ts = sqlite_repo_with_project.add_time_slot("09:00")
    new_ts = sqlite_repo_with_project.add_time_slot("11:00", "Late")
    hint = sqlite_repo_with_project.add_hint(HintType.constraint, "Keep distance")
    assert sqlite_repo_with_project.update_hint(hint.id, content="Updated constraint") is True
    ignored = sqlite_repo_with_project.ignore_entity(EntityKind.location, " Basement ")
    merged_char = sqlite_repo_with_project.merge_character("Ali", char.id)
    merged_loc = sqlite_repo_with_project.merge_location("Lib", loc.id)

    assert updated_script is not None and updated_script.title == "Scene 2"
    assert fact.source_script_ids == [script.id]
    assert duplicate_ts is None
    assert new_ts is not None and new_ts.description == "Late"
    assert sqlite_repo_with_project.get_time_slot_label(new_ts.id) == "11:00 (Late)"
    assert sqlite_repo_with_project.is_entity_ignored(EntityKind.location, "basement") is True
    assert ignored.name == "Basement"
    assert "Ali" in merged_char.aliases
    assert "Lib" in merged_loc.aliases

    assert sqlite_repo_with_project.remove_fact(fact.id) is True
    assert sqlite_repo_with_project.remove_script(script.id) is True
    assert sqlite_repo_with_project.remove_hint(hint.id) is True
    assert sqlite_repo_with_project.remove_time_slot(new_ts.id) is True
    assert sqlite_repo_with_project.remove_character(char.id) is True
    assert sqlite_repo_with_project.remove_location(loc.id) is True


def test_app_state_uses_sqlite_backend_factory(sqlite_state):
    project = sqlite_state.create_project("Factory", time_slots=["09:00"])
    char = sqlite_state.add_character("Alice")
    sqlite_state.add_location("Library")

    sqlite_state.current_project = None
    sqlite_state.load_project(project.id)

    assert sqlite_state.current_project is not None
    assert sqlite_state.current_project.characters[0].id == char.id
    assert isinstance(sqlite_state.store, SQLiteStore)


def test_app_state_defaults_to_sqlite_backend(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = AppState()
    project = state.create_project("默认SQLite", time_slots=["09:00"])

    assert isinstance(state.store, SQLiteStore)
    assert state.store.db_path.name == "projects.db"
    assert state.store.db_path.exists()

    state.current_project = None
    state.load_project(project.id)
    assert state.current_project is not None
    assert state.current_project.id == project.id


def test_app_state_list_projects_ignores_corrupt_summary_rows(sqlite_state):
    valid_project = sqlite_state.create_project("有效项目")
    sqlite_state.current_project = None

    import sqlite3

    with sqlite3.connect(sqlite_state.store.db_path) as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, name, description, created_at, updated_at,
                character_count, location_count, script_count, fact_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "broken-row",
                "损坏行",
                "bad timestamps",
                "bad-value",
                "bad-value",
                0,
                0,
                0,
                0,
            ),
        )
        conn.commit()

    summaries = sqlite_state.list_projects()

    assert [summary.id for summary in summaries] == [valid_project.id]


def test_edited_project_reload_and_recency_metadata(sqlite_state):
    first = sqlite_state.create_project("较早项目")
    first_id = first.id
    sqlite_state.current_project = None

    second = sqlite_state.create_project("最近项目")
    second_id = second.id
    original_second_updated_at = second.updated_at

    edited_char = sqlite_state.add_character("Alice")
    sqlite_state.update_character(edited_char.id, name="Alice Updated")
    edited_updated_at = sqlite_state.current_project.updated_at

    sqlite_state.current_project = None
    summaries = sqlite_state.list_projects()

    assert [summary.id for summary in summaries[:2]] == [second_id, first_id]
    second_summary = next(summary for summary in summaries if summary.id == second_id)
    assert second_summary.updated_at >= edited_updated_at
    assert second_summary.updated_at > original_second_updated_at

    sqlite_state.load_project(second_id)
    assert sqlite_state.current_project is not None
    assert sqlite_state.current_project.characters[0].name == "Alice Updated"


def test_add_deduction_blocked_by_fact_pending_and_rejection(sqlite_repo_with_project):
    char = sqlite_repo_with_project.add_character("Alice")
    loc = sqlite_repo_with_project.add_location("Library")
    ts1 = sqlite_repo_with_project.current_project.time_slots[0]
    ts2 = sqlite_repo_with_project.current_project.time_slots[1]

    sqlite_repo_with_project.add_fact(char.id, loc.id, ts1.id)
    ded_pending = _make_deduction(char.id, loc.id, ts2.id)
    ded_rejected = _make_deduction(char.id, loc.id, "custom-ts")

    assert sqlite_repo_with_project.add_deduction(_make_deduction(char.id, loc.id, ts1.id)) is False
    assert sqlite_repo_with_project.add_deduction(ded_pending) is True
    assert sqlite_repo_with_project.add_deduction(_make_deduction(char.id, loc.id, ts2.id)) is False
    assert sqlite_repo_with_project.add_deduction(ded_rejected) is True
    sqlite_repo_with_project.reject_deduction(ded_rejected.id)
    assert sqlite_repo_with_project.add_deduction(
        _make_deduction(char.id, loc.id, ded_rejected.time_slot)
    ) is False


def test_accept_reject_clear_pending_and_reload_parity(sqlite_repo_with_project):
    char = sqlite_repo_with_project.add_character("Alice")
    loc = sqlite_repo_with_project.add_location("Library")
    ts1 = sqlite_repo_with_project.current_project.time_slots[0]
    ts2 = sqlite_repo_with_project.current_project.time_slots[1]

    ded_accept = _make_deduction(char.id, loc.id, ts1.id, supporting_script_ids=["script-a"])
    ded_reject = _make_deduction(char.id, loc.id, ts2.id)
    ded_clear = _make_deduction(char.id, loc.id, "clear-slot")

    sqlite_repo_with_project.add_deduction(ded_accept)
    sqlite_repo_with_project.add_deduction(ded_reject)
    sqlite_repo_with_project.add_deduction(ded_clear)

    fact = sqlite_repo_with_project.accept_deduction(ded_accept.id)
    rejection = sqlite_repo_with_project.reject_deduction(ded_reject.id, reason="")
    removed = sqlite_repo_with_project.clear_pending_deductions()
    project_id = sqlite_repo_with_project.current_project.id

    assert fact is not None
    assert fact.from_deduction_id == ded_accept.id
    assert fact.source_script_ids == ["script-a"]
    assert rejection is not None
    assert rejection.reason == "用户拒绝"
    assert rejection.from_deduction_id == ded_reject.id
    assert removed == 1
    assert sqlite_repo_with_project.get_pending_deductions() == []
    assert ded_accept.status.value == "accepted"
    assert ded_reject.status.value == "rejected"

    sqlite_repo_with_project.current_project = None
    sqlite_repo_with_project.load_project(project_id)
    loaded = sqlite_repo_with_project.current_project
    loaded_fact = next(f for f in loaded.facts if f.from_deduction_id == ded_accept.id)
    loaded_rejection = next(r for r in loaded.rejections if r.from_deduction_id == ded_reject.id)
    loaded_ded_accept = next(d for d in loaded.deductions if d.id == ded_accept.id)
    loaded_ded_reject = next(d for d in loaded.deductions if d.id == ded_reject.id)

    assert loaded_fact.id == fact.id
    assert loaded_rejection.id == rejection.id
    assert loaded_ded_accept.status.value == "accepted"
    assert loaded_ded_reject.status.value == "rejected"
    assert sqlite_repo_with_project.add_deduction(_make_deduction(char.id, loc.id, ts1.id)) is False
    assert sqlite_repo_with_project.add_deduction(_make_deduction(char.id, loc.id, ts2.id)) is False
    assert sqlite_repo_with_project.add_deduction(_make_deduction(char.id, loc.id, ded_clear.time_slot))
    assert sqlite_repo_with_project.add_deduction(_make_deduction(char.id, loc.id, ded_clear.time_slot)) is False


def test_cascade_delete_and_script_cleanup_persist_across_reload(sqlite_repo_with_project):
    alice = sqlite_repo_with_project.add_character("Alice")
    bob = sqlite_repo_with_project.add_character("Bob")
    library = sqlite_repo_with_project.add_location("Library")
    kitchen = sqlite_repo_with_project.add_location("Kitchen")
    ts1 = sqlite_repo_with_project.current_project.time_slots[0]
    ts2 = sqlite_repo_with_project.current_project.time_slots[1]
    script_to_remove = sqlite_repo_with_project.add_script("scene", title="Scene")
    metadata_script = sqlite_repo_with_project.add_script("metadata", title="Metadata")
    metadata_script.metadata.characters_mentioned = ["Alice", "Bob"]
    sqlite_repo_with_project.save()

    sqlite_repo_with_project.add_fact(
        alice.id, library.id, ts1.id, source_script_ids=[script_to_remove.id]
    )
    surviving_fact = sqlite_repo_with_project.add_fact(bob.id, kitchen.id, ts2.id)
    ded_char = _make_deduction(
        alice.id, kitchen.id, ts2.id, supporting_script_ids=[script_to_remove.id]
    )
    ded_loc = _make_deduction(bob.id, library.id, ts2.id)
    ded_ts = _make_deduction(bob.id, kitchen.id, ts1.id)
    ded_rej = _make_deduction(alice.id, library.id, "rej-ts")
    sqlite_repo_with_project.add_deduction(ded_char)
    sqlite_repo_with_project.add_deduction(ded_loc)
    sqlite_repo_with_project.add_deduction(ded_ts)
    sqlite_repo_with_project.add_deduction(ded_rej)
    sqlite_repo_with_project.reject_deduction(ded_rej.id)

    assert sqlite_repo_with_project.remove_script(script_to_remove.id) is True
    assert script_to_remove.id not in surviving_fact.source_script_ids
    assert script_to_remove.id not in ded_char.supporting_script_ids

    assert sqlite_repo_with_project.remove_character(alice.id) is True
    assert "Alice" not in sqlite_repo_with_project.current_project.scripts[0].metadata.characters_mentioned
    assert sqlite_repo_with_project.remove_location(library.id) is True
    assert sqlite_repo_with_project.remove_time_slot(ts1.id) is True

    project_id = sqlite_repo_with_project.current_project.id
    sqlite_repo_with_project.current_project = None
    sqlite_repo_with_project.load_project(project_id)
    loaded = sqlite_repo_with_project.current_project

    assert {c.id for c in loaded.characters} == {bob.id}
    assert {location.id for location in loaded.locations} == {kitchen.id}
    assert {t.id for t in loaded.time_slots} == {ts2.id}
    assert [f.id for f in loaded.facts] == [surviving_fact.id]
    assert loaded.facts[0].character_id == bob.id
    assert loaded.facts[0].location_id == kitchen.id
    assert loaded.facts[0].source_script_ids == []
    assert all(d.character_id != alice.id for d in loaded.deductions)
    assert all(d.location_id != library.id for d in loaded.deductions)
    assert all(d.time_slot != ts1.id for d in loaded.deductions)
    assert loaded.rejections == []
    assert len(loaded.scripts) == 1
    assert "Alice" not in loaded.scripts[0].metadata.characters_mentioned
