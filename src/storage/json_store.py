"""JSON file-based storage layer for Project data.

Each project is stored as a single JSON file: data/{project_id}.json
Uses Pydantic v2 model_dump_json() / model_validate_json() for serialization.
"""

import os
from pathlib import Path

from src.models.puzzle import Project, ProjectSummary


class JsonStore:
    """Manages Project persistence using JSON files on disk."""

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            # Default to data/ in the project root
            data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self.data_dir = Path(data_dir)
        self._ensure_data_dir()

    def _ensure_data_dir(self) -> None:
        """Create the data directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _project_path(self, project_id: str) -> Path:
        """Get the file path for a project by ID."""
        return self.data_dir / f"{project_id}.json"

    def list_projects(self) -> list[ProjectSummary]:
        """List all projects as lightweight summaries."""
        summaries = []
        for file_path in sorted(self.data_dir.glob("*.json")):
            try:
                json_data = file_path.read_text(encoding="utf-8")
                project = Project.model_validate_json(json_data)
                summary = ProjectSummary(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    character_count=len(project.characters),
                    location_count=len(project.locations),
                    script_count=len(project.scripts),
                    fact_count=len(project.facts),
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
                summaries.append(summary)
            except Exception:
                # Skip corrupted files
                continue
        return summaries

    def load_project(self, project_id: str) -> Project:
        """Load a project by its ID.

        Raises:
            FileNotFoundError: If the project file doesn't exist.
            ValueError: If the file contains invalid data.
        """
        file_path = self._project_path(project_id)
        if not file_path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        json_data = file_path.read_text(encoding="utf-8")
        return Project.model_validate_json(json_data)

    def save_project(self, project: Project) -> None:
        """Save a project to disk. Overwrites existing file if present."""
        self._ensure_data_dir()
        file_path = self._project_path(project.id)
        json_data = project.model_dump_json(indent=2)
        file_path.write_text(json_data, encoding="utf-8")

    def create_project(
        self,
        name: str,
        description: str | None = None,
        time_slots: list[str] | None = None,
    ) -> Project:
        """Create a new project and save it to disk.

        Args:
            name: Project name.
            description: Optional project description.
            time_slots: List of time slots in HH:MM format.

        Returns:
            The newly created Project.
        """
        project = Project(
            name=name,
            description=description,
            time_slots=time_slots or [],
        )
        self.save_project(project)
        return project

    def delete_project(self, project_id: str) -> None:
        """Delete a project file.

        Raises:
            FileNotFoundError: If the project file doesn't exist.
        """
        file_path = self._project_path(project_id)
        if not file_path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        os.remove(file_path)
