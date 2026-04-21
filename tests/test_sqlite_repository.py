import pytest

from src.models.puzzle import CharacterStatus, EntityKind, HintType
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
