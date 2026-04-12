"""Tests for the JSON storage layer."""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.models.puzzle import Project, Character, Location, Fact, SourceType
from src.storage.json_store import JsonStore


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    temp_dir = tempfile.mkdtemp(prefix="puzzle_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def store(temp_data_dir):
    """Create a JsonStore with a temporary data directory."""
    return JsonStore(data_dir=temp_data_dir)


class TestJsonStore:
    def test_create_project(self, store):
        project = store.create_project(
            name="Test Mystery",
            description="A test game",
            time_slots=["14:00", "15:00", "16:00"],
        )
        assert project.name == "Test Mystery"
        assert project.description == "A test game"
        assert len(project.time_slots) == 3
        # File should exist on disk
        file_path = store.data_dir / f"{project.id}.json"
        assert file_path.exists()

    def test_load_project(self, store):
        project = store.create_project(name="Load Test")
        loaded = store.load_project(project.id)
        assert loaded.name == project.name
        assert loaded.id == project.id

    def test_load_nonexistent_project(self, store):
        with pytest.raises(FileNotFoundError):
            store.load_project("nonexistent-id")

    def test_save_and_load_with_entities(self, store):
        project = store.create_project(
            name="Full Test",
            time_slots=["14:00", "15:00"],
        )

        # Add entities
        char = Character(name="Alice")
        loc = Location(name="Library")
        fact = Fact(
            character_id=char.id,
            location_id=loc.id,
            time_slot="14:00",
            source_type=SourceType.user_input,
        )
        project.characters.append(char)
        project.locations.append(loc)
        project.facts.append(fact)

        store.save_project(project)
        loaded = store.load_project(project.id)

        assert len(loaded.characters) == 1
        assert loaded.characters[0].name == "Alice"
        assert len(loaded.locations) == 1
        assert loaded.locations[0].name == "Library"
        assert len(loaded.facts) == 1
        assert loaded.facts[0].time_slot == "14:00"

    def test_list_projects(self, store):
        store.create_project(name="Project A")
        store.create_project(name="Project B")
        store.create_project(name="Project C")

        summaries = store.list_projects()
        assert len(summaries) == 3
        names = {s.name for s in summaries}
        assert "Project A" in names
        assert "Project B" in names
        assert "Project C" in names

    def test_list_projects_empty(self, store):
        summaries = store.list_projects()
        assert summaries == []

    def test_delete_project(self, store):
        project = store.create_project(name="To Delete")
        file_path = store.data_dir / f"{project.id}.json"
        assert file_path.exists()

        store.delete_project(project.id)
        assert not file_path.exists()

    def test_delete_nonexistent_project(self, store):
        with pytest.raises(FileNotFoundError):
            store.delete_project("nonexistent-id")

    def test_overwrite_on_save(self, store):
        project = store.create_project(name="Original Name")
        project.name = "Updated Name"
        store.save_project(project)

        loaded = store.load_project(project.id)
        assert loaded.name == "Updated Name"

    def test_auto_creates_data_dir(self, temp_data_dir):
        nested_dir = temp_data_dir / "nested" / "deep"
        store = JsonStore(data_dir=nested_dir)
        assert nested_dir.exists()
        # Can still create projects
        project = store.create_project(name="Nested Test")
        assert (nested_dir / f"{project.id}.json").exists()
