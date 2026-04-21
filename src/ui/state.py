"""App state management — singleton that holds the current project.

All UI mutations go through AppState methods which handle persistence.
The Flet UI layer will call page.update() directly after state changes.

AppState is a thin coordinator: it holds a JsonRepository instance and
delegates all data operations to it.  Public method signatures remain
identical to the original implementation so that existing callers
(UI pages, tests, services) are unaffected.
"""

from __future__ import annotations

from pathlib import Path

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
    Rejection,
    Script,
    SourceType,
    TimeSlot,
)
from src.storage.cache_manager import CacheManager
from src.storage.json_repository import JsonRepository
from src.storage.json_store import JsonStore
from src.storage.repository import Repository
from src.storage.sqlite_repository import SQLiteRepository
from src.storage.sqlite_store import SQLiteStore


def _make_repository(store: JsonStore | SQLiteStore | None = None) -> Repository:
    if isinstance(store, SQLiteStore):
        return SQLiteRepository(store=store)
    return JsonRepository(store=store)


class AppState:
    """Manages the currently loaded project and provides state access.

    Internally delegates all data operations to a :class:`JsonRepository`.
    """

    def __init__(self, store: JsonStore | SQLiteStore | None = None) -> None:
        self._repo = _make_repository(store=store)

    # ------------------------------------------------------------------
    # Backward-compatibility attributes
    # ------------------------------------------------------------------

    @property
    def store(self) -> JsonStore | SQLiteStore:
        """Expose the underlying store for callers that access it directly."""
        return self._repo.store

    @property
    def cache(self) -> CacheManager:
        """Expose the CacheManager for centralized index lookups.

        UI pages and services should use this instead of building ad-hoc
        lookup maps.  Common indexes available:

        - ``cache.char_by_id``   : {char_id: Character}
        - ``cache.loc_by_id``    : {loc_id: Location}
        - ``cache.ts_by_id``     : {ts_id: TimeSlot}
        - ``cache.char_by_name`` : {name.lower(): Character}
        - ``cache.loc_by_name``  : {name.lower(): Location}
        - ``cache.ts_label_map`` : {label_str: ts_id}
        - ``cache.rejection_map``: {from_deduction_id: reason}
        """
        return self._repo._cache

    @property
    def current_project(self) -> Project | None:
        """The currently loaded project (delegates to repository)."""
        return self._repo.current_project

    @current_project.setter
    def current_project(self, value: Project | None) -> None:
        self._repo.current_project = value

    # Deduplication index proxies — some tests read/write these directly.

    @property
    def _fact_index(self) -> set[tuple[str, str, str]]:
        return self._repo._cache.fact_index

    @_fact_index.setter
    def _fact_index(self, value: set[tuple[str, str, str]]) -> None:
        self._repo._cache.fact_index = value

    @property
    def _pending_index(self) -> set[tuple[str, str, str]]:
        return self._repo._cache.pending_index

    @_pending_index.setter
    def _pending_index(self, value: set[tuple[str, str, str]]) -> None:
        self._repo._cache.pending_index = value

    @property
    def _rejection_index(self) -> set[tuple[str, str, str]]:
        return self._repo._cache.rejection_index

    @_rejection_index.setter
    def _rejection_index(self, value: set[tuple[str, str, str]]) -> None:
        self._repo._cache.rejection_index = value

    def _rebuild_indexes(self) -> None:
        """Rebuild all deduplication indexes from current project data."""
        self._repo._rebuild_indexes()

    # ------------------------------------------------------------------
    # Project management (delegates to repository)
    # ------------------------------------------------------------------

    def load_project(self, project_id: str) -> None:
        """Load a project by ID and set it as the current project."""
        self._repo.load_project(project_id)

    def save(self) -> None:
        """Save the current project to disk."""
        self._repo.save()

    def create_project(
        self,
        name: str,
        description: str | None = None,
        time_slots: list[str] | None = None,
    ) -> Project:
        """Create a new project, save it, and set it as current."""
        return self._repo.create_project(
            name=name,
            description=description,
            time_slots=time_slots,
        )

    def delete_project(self, project_id: str) -> None:
        """Delete a project. If it's the current project, unset it."""
        self._repo.delete_project(project_id)

    def list_projects(self):
        """List all available projects as summaries."""
        return self._repo.list_projects()

    def import_project_from_json(self, json_path: str | Path) -> Project:
        """Import one user-selected legacy JSON project into active storage."""
        if not isinstance(self.store, SQLiteStore):
            raise NotImplementedError("JSON import is only supported for SQLite-backed storage")
        return self._repo.import_project_from_json(json_path)

    # ------------------------------------------------------------------
    # Character management
    # ------------------------------------------------------------------

    def add_character(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus = CharacterStatus.confirmed,
    ) -> Character:
        """Add a character to the current project."""
        return self._repo.add_character(
            name=name,
            aliases=aliases,
            description=description,
            status=status,
        )

    def update_character(
        self,
        character_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus | None = None,
    ) -> Character | None:
        """Update a character's fields. Returns the updated character or None."""
        return self._repo.update_character(
            character_id=character_id,
            name=name,
            aliases=aliases,
            description=description,
            status=status,
        )

    def remove_character(self, character_id: str) -> bool:
        """Remove a character by ID. Returns True if found and removed."""
        return self._repo.remove_character(character_id)

    # ------------------------------------------------------------------
    # Location management
    # ------------------------------------------------------------------

    def add_location(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location:
        """Add a location to the current project."""
        return self._repo.add_location(
            name=name,
            aliases=aliases,
            description=description,
        )

    def update_location(
        self,
        location_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location | None:
        """Update a location's fields. Returns the updated location or None."""
        return self._repo.update_location(
            location_id=location_id,
            name=name,
            aliases=aliases,
            description=description,
        )

    def remove_location(self, location_id: str) -> bool:
        """Remove a location by ID. Returns True if found and removed."""
        return self._repo.remove_location(location_id)

    # ------------------------------------------------------------------
    # Script management
    # ------------------------------------------------------------------

    def add_script(
        self,
        raw_text: str,
        title: str | None = None,
        user_notes: str | None = None,
        stated_time: str | None = None,
        stated_location: str | None = None,
    ) -> Script:
        """Add a script to the current project."""
        return self._repo.add_script(
            raw_text=raw_text,
            title=title,
            user_notes=user_notes,
            stated_time=stated_time,
            stated_location=stated_location,
        )

    def update_script(
        self,
        script_id: str,
        title: str | None = None,
        raw_text: str | None = None,
        user_notes: str | None = None,
    ) -> Script | None:
        """Update a script's fields. Returns the updated script or None."""
        return self._repo.update_script(
            script_id=script_id,
            title=title,
            raw_text=raw_text,
            user_notes=user_notes,
        )

    def save_script_analysis(self, script_id: str, result: dict) -> bool:
        """Save analysis result to a script. Returns True if saved."""
        return self._repo.save_script_analysis(script_id, result)

    def remove_script(self, script_id: str) -> bool:
        """Remove a script by ID. Returns True if found and removed."""
        return self._repo.remove_script(script_id)

    # ------------------------------------------------------------------
    # Fact management
    # ------------------------------------------------------------------

    def add_fact(
        self,
        character_id: str,
        location_id: str,
        time_slot: str,
        source_type: SourceType = SourceType.user_input,
        source_evidence: str | None = None,
        source_script_ids: list[str] | None = None,
    ) -> Fact:
        """Add a fact to the current project."""
        return self._repo.add_fact(
            character_id=character_id,
            location_id=location_id,
            time_slot=time_slot,
            source_type=source_type,
            source_evidence=source_evidence,
            source_script_ids=source_script_ids,
        )

    def remove_fact(self, fact_id: str) -> bool:
        """Remove a fact by ID. Returns True if found and removed."""
        return self._repo.remove_fact(fact_id)

    # ------------------------------------------------------------------
    # Time slot management
    # ------------------------------------------------------------------

    def add_time_slot(self, time_slot: str, description: str = "") -> TimeSlot | None:
        """Add a time slot. Validates HH:MM format. Returns TimeSlot if added, None if duplicate."""
        return self._repo.add_time_slot(time_slot, description)

    def remove_time_slot(self, time_slot_id: str) -> bool:
        """Remove a time slot by ID. Returns True if found and removed."""
        return self._repo.remove_time_slot(time_slot_id)

    def reorder_time_slot(self, time_slot_id: str, direction: int) -> bool:
        """Move a time slot up (direction=-1) or down (direction=1) in sort order.

        Returns True if the time slot was moved, False otherwise.
        """
        return self._repo.reorder_time_slot(time_slot_id, direction)

    def get_time_slot_by_id(self, ts_id: str) -> TimeSlot | None:
        """Look up a time slot by ID. Returns None if not found."""
        return self._repo.get_time_slot_by_id(ts_id)

    def get_time_slot_label(self, ts_id: str) -> str:
        """Return display label for a time slot ID.

        Returns 'label (description)' if description is non-empty,
        otherwise just 'label'. Falls back to raw ID if not found.
        """
        return self._repo.get_time_slot_label(ts_id)

    # ------------------------------------------------------------------
    # Hint management
    # ------------------------------------------------------------------

    def add_hint(
        self,
        hint_type: HintType,
        content: str,
    ) -> Hint:
        """Add a hint/rule/constraint to the current project."""
        return self._repo.add_hint(hint_type, content)

    def update_hint(
        self,
        hint_id: str,
        hint_type: HintType | None = None,
        content: str | None = None,
    ) -> bool:
        """Update a hint's type and/or content. Returns True if found and updated."""
        return self._repo.update_hint(hint_id, hint_type=hint_type, content=content)

    def remove_hint(self, hint_id: str) -> bool:
        """Remove a hint by ID. Returns True if found and removed."""
        return self._repo.remove_hint(hint_id)

    # ------------------------------------------------------------------
    # Ignored entity management
    # ------------------------------------------------------------------

    def ignore_entity(self, kind: EntityKind, name: str) -> IgnoredEntity:
        """Permanently ignore a raw entity name so it won't be suggested again."""
        return self._repo.ignore_entity(kind, name)

    def is_entity_ignored(self, kind: EntityKind, name: str) -> bool:
        """Return True if this raw name has been ignored for the given kind."""
        return self._repo.is_entity_ignored(kind, name)

    # ------------------------------------------------------------------
    # Entity merge
    # ------------------------------------------------------------------

    def merge_character(self, source_name: str, target_id: str) -> Character | None:
        """Merge source_name into an existing character by adding it as an alias.

        Does not create a new character — the source name becomes an alias of target.
        Returns the updated target character.
        """
        return self._repo.merge_character(source_name, target_id)

    def merge_location(self, source_name: str, target_id: str) -> Location | None:
        """Merge source_name into an existing location by adding it as an alias.

        Returns the updated target location.
        """
        return self._repo.merge_location(source_name, target_id)

    # ------------------------------------------------------------------
    # Deduction management
    # ------------------------------------------------------------------

    def add_deduction(self, deduction: Deduction) -> bool:
        """Add a pending deduction to the current project.

        Checks if the (character_id, location_id, time_slot) triple already exists
        as a confirmed Fact, pending Deduction, or Rejection. If so, silently skips.

        Returns:
            True if the deduction was added, False if it was skipped as a duplicate.
        """
        return self._repo.add_deduction(deduction)

    def accept_deduction(self, deduction_id: str) -> Fact | None:
        """Accept a deduction: create a Fact from it, mark it accepted."""
        return self._repo.accept_deduction(deduction_id)

    def reject_deduction(self, deduction_id: str, reason: str = "") -> Rejection | None:
        """Reject a deduction: create a Rejection record, mark it rejected."""
        return self._repo.reject_deduction(deduction_id, reason)

    def get_pending_deductions(self) -> list[Deduction]:
        """Return list of pending deductions."""
        return self._repo.get_pending_deductions()

    def clear_pending_deductions(self) -> int:
        """Remove all pending deductions. Returns count removed."""
        return self._repo.clear_pending_deductions()


# Module-level singleton instance
app_state = AppState()
