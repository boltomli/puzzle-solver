"""Repository Protocol — typed interface for all data access operations.

Defines the contract that any data backend must satisfy.
Framework-agnostic: no flet imports, fully testable with plain pytest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.models.puzzle import (
        Character,
        CharacterStatus,
        Deduction,
        EntityKind,
        Fact,
        Hint,
        HintType,
        IgnoredEntity,
        Location,
        Project,
        ProjectSummary,
        Rejection,
        Script,
        SourceType,
        TimeSlot,
    )


@runtime_checkable
class Repository(Protocol):
    """Typed interface for all puzzle project data access operations.

    Method signatures match the current AppState public API exactly.
    All implementations must be framework-agnostic (no flet imports).
    """

    # --- Project lifecycle ---

    def load_project(self, project_id: str) -> None:
        """Load a project by ID and set it as the current project."""
        ...

    def save(self) -> None:
        """Save the current project to disk."""
        ...

    def create_project(
        self,
        name: str,
        description: str | None = None,
        time_slots: list[str] | None = None,
    ) -> Project:
        """Create a new project, save it, and set it as current."""
        ...

    def delete_project(self, project_id: str) -> None:
        """Delete a project. If it's the current project, unset it."""
        ...

    def list_projects(self) -> list[ProjectSummary]:
        """List all available projects as summaries."""
        ...

    # --- Character management ---

    def add_character(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus = ...,
    ) -> Character:
        """Add a character to the current project."""
        ...

    def update_character(
        self,
        character_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus | None = None,
    ) -> Character | None:
        """Update a character's fields. Returns the updated character or None."""
        ...

    def remove_character(self, character_id: str) -> bool:
        """Remove a character by ID. Returns True if found and removed."""
        ...

    # --- Location management ---

    def add_location(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location:
        """Add a location to the current project."""
        ...

    def update_location(
        self,
        location_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location | None:
        """Update a location's fields. Returns the updated location or None."""
        ...

    def remove_location(self, location_id: str) -> bool:
        """Remove a location by ID. Returns True if found and removed."""
        ...

    # --- Script management ---

    def add_script(
        self,
        raw_text: str,
        title: str | None = None,
        user_notes: str | None = None,
        stated_time: str | None = None,
        stated_location: str | None = None,
    ) -> Script:
        """Add a script to the current project."""
        ...

    def update_script(
        self,
        script_id: str,
        title: str | None = None,
        raw_text: str | None = None,
        user_notes: str | None = None,
    ) -> Script | None:
        """Update a script's fields. Returns the updated script or None."""
        ...

    def save_script_analysis(self, script_id: str, result: dict) -> bool:
        """Save analysis result to a script. Returns True if saved."""
        ...

    def remove_script(self, script_id: str) -> bool:
        """Remove a script by ID. Returns True if found and removed."""
        ...

    # --- Fact management ---

    def add_fact(
        self,
        character_id: str,
        location_id: str,
        time_slot: str,
        source_type: SourceType = ...,
        source_evidence: str | None = None,
        source_script_ids: list[str] | None = None,
    ) -> Fact:
        """Add a fact to the current project."""
        ...

    def remove_fact(self, fact_id: str) -> bool:
        """Remove a fact by ID. Returns True if found and removed."""
        ...

    # --- Time slot management ---

    def add_time_slot(self, time_slot: str, description: str = "") -> TimeSlot | None:
        """Add a time slot. Validates HH:MM format. Returns TimeSlot if added, None if duplicate."""
        ...

    def remove_time_slot(self, time_slot_id: str) -> bool:
        """Remove a time slot by ID. Returns True if found and removed."""
        ...

    def reorder_time_slot(self, time_slot_id: str, direction: int) -> bool:
        """Move a time slot up (direction=-1) or down (direction=1) in sort order."""
        ...

    def get_time_slot_by_id(self, ts_id: str) -> TimeSlot | None:
        """Look up a time slot by ID. Returns None if not found."""
        ...

    def get_time_slot_label(self, ts_id: str) -> str:
        """Return display label for a time slot ID."""
        ...

    # --- Hint management ---

    def add_hint(self, hint_type: HintType, content: str) -> Hint:
        """Add a hint/rule/constraint to the current project."""
        ...

    def remove_hint(self, hint_id: str) -> bool:
        """Remove a hint by ID. Returns True if found and removed."""
        ...

    # --- Ignored entity management ---

    def ignore_entity(self, kind: EntityKind, name: str) -> IgnoredEntity:
        """Permanently ignore a raw entity name so it won't be suggested again."""
        ...

    def is_entity_ignored(self, kind: EntityKind, name: str) -> bool:
        """Return True if this raw name has been ignored for the given kind."""
        ...

    # --- Entity merge ---

    def merge_character(self, source_name: str, target_id: str) -> Character | None:
        """Merge source_name into an existing character by adding it as an alias."""
        ...

    def merge_location(self, source_name: str, target_id: str) -> Location | None:
        """Merge source_name into an existing location by adding it as an alias."""
        ...

    # --- Deduction management ---

    def add_deduction(self, deduction: Deduction) -> bool:
        """Add a pending deduction. Returns True if added, False if duplicate."""
        ...

    def accept_deduction(self, deduction_id: str) -> Fact | None:
        """Accept a deduction: create a Fact from it, mark it accepted."""
        ...

    def reject_deduction(self, deduction_id: str, reason: str = "") -> Rejection | None:
        """Reject a deduction: create a Rejection record, mark it rejected."""
        ...

    def get_pending_deductions(self) -> list[Deduction]:
        """Return list of pending deductions."""
        ...

    def clear_pending_deductions(self) -> int:
        """Remove all pending deductions. Returns count removed."""
        ...
