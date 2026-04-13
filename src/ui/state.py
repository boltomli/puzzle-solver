"""App state management — singleton that holds the current project and provides reactive updates.

All UI mutations go through AppState methods which handle persistence and notification.
"""

import re
from datetime import datetime
from typing import Callable, Optional

from src.models.puzzle import (
    Character,
    CharacterStatus,
    Deduction,
    DeductionStatus,
    Fact,
    Hint,
    HintType,
    Location,
    Project,
    Rejection,
    Script,
    ScriptMetadata,
    SourceType,
)
from src.storage.json_store import JsonStore


class AppState:
    """Manages the currently loaded project and provides reactive state."""

    def __init__(self, store: JsonStore | None = None):
        self.store = store or JsonStore()
        self.current_project: Optional[Project] = None
        self._on_change_callbacks: list[Callable] = []
        self._on_data_change_callbacks: list[Callable] = []

    # --- Reactive notification ---

    def on_change(self, callback: Callable) -> None:
        """Register a callback for project-level changes (load/create/delete)."""
        self._on_change_callbacks.append(callback)

    def on_data_change(self, callback: Callable) -> None:
        """Register a callback for entity-level data changes."""
        self._on_data_change_callbacks.append(callback)

    def clear_callbacks(self) -> None:
        """Clear all registered callbacks. Called on page load to prevent accumulation."""
        self._on_change_callbacks.clear()
        self._on_data_change_callbacks.clear()

    def _notify(self) -> None:
        """Notify project-level callbacks (full UI refresh)."""
        for cb in self._on_change_callbacks:
            try:
                cb()
            except Exception:
                pass  # Don't let a bad callback break the chain

    def _notify_data(self) -> None:
        """Notify data-level callbacks (partial refresh only)."""
        for cb in self._on_data_change_callbacks:
            try:
                cb()
            except Exception:
                pass  # Don't let a bad callback break the chain

    # --- Project management ---

    def load_project(self, project_id: str) -> None:
        """Load a project by ID and set it as the current project."""
        self.current_project = self.store.load_project(project_id)
        self._notify()

    def save(self) -> None:
        """Save the current project to disk."""
        if self.current_project:
            self.current_project.updated_at = datetime.now()
            self.store.save_project(self.current_project)

    def create_project(
        self,
        name: str,
        description: str | None = None,
        time_slots: list[str] | None = None,
    ) -> Project:
        """Create a new project, save it, and set it as current."""
        project = self.store.create_project(
            name=name,
            description=description,
            time_slots=time_slots or [],
        )
        self.current_project = project
        self._notify()
        return project

    def delete_project(self, project_id: str) -> None:
        """Delete a project. If it's the current project, unset it."""
        self.store.delete_project(project_id)
        if self.current_project and self.current_project.id == project_id:
            self.current_project = None
        self._notify()

    def list_projects(self):
        """List all available projects as summaries."""
        return self.store.list_projects()

    # --- Character management ---

    def add_character(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus = CharacterStatus.confirmed,
    ) -> Character:
        """Add a character to the current project."""
        if not self.current_project:
            raise ValueError("No project loaded")
        char = Character(
            name=name,
            aliases=aliases or [],
            description=description,
            status=status,
        )
        self.current_project.characters.append(char)
        self.save()
        self._notify_data()
        return char

    def update_character(
        self,
        character_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus | None = None,
    ) -> Character | None:
        """Update a character's fields. Returns the updated character or None."""
        if not self.current_project:
            raise ValueError("No project loaded")
        for char in self.current_project.characters:
            if char.id == character_id:
                if name is not None:
                    char.name = name
                if aliases is not None:
                    char.aliases = aliases
                if description is not None:
                    char.description = description
                if status is not None:
                    char.status = status
                self.save()
                self._notify_data()
                return char
        return None

    def remove_character(self, character_id: str) -> bool:
        """Remove a character by ID. Returns True if found and removed."""
        if not self.current_project:
            raise ValueError("No project loaded")
        original_len = len(self.current_project.characters)
        self.current_project.characters = [
            c for c in self.current_project.characters if c.id != character_id
        ]
        if len(self.current_project.characters) < original_len:
            self.save()
            self._notify_data()
            return True
        return False

    # --- Location management ---

    def add_location(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location:
        """Add a location to the current project."""
        if not self.current_project:
            raise ValueError("No project loaded")
        loc = Location(
            name=name,
            aliases=aliases or [],
            description=description,
        )
        self.current_project.locations.append(loc)
        self.save()
        self._notify_data()
        return loc

    def update_location(
        self,
        location_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location | None:
        """Update a location's fields. Returns the updated location or None."""
        if not self.current_project:
            raise ValueError("No project loaded")
        for loc in self.current_project.locations:
            if loc.id == location_id:
                if name is not None:
                    loc.name = name
                if aliases is not None:
                    loc.aliases = aliases
                if description is not None:
                    loc.description = description
                self.save()
                self._notify_data()
                return loc
        return None

    def remove_location(self, location_id: str) -> bool:
        """Remove a location by ID. Returns True if found and removed."""
        if not self.current_project:
            raise ValueError("No project loaded")
        original_len = len(self.current_project.locations)
        self.current_project.locations = [
            loc for loc in self.current_project.locations if loc.id != location_id
        ]
        if len(self.current_project.locations) < original_len:
            self.save()
            self._notify_data()
            return True
        return False

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
        if not self.current_project:
            raise ValueError("No project loaded")
        metadata = ScriptMetadata(
            stated_time=stated_time,
            stated_location=stated_location,
            user_notes=user_notes,
            source_order=len(self.current_project.scripts) + 1,
        )
        script = Script(
            title=title,
            raw_text=raw_text,
            metadata=metadata,
        )
        self.current_project.scripts.append(script)
        self.save()
        self._notify_data()
        return script

    def update_script(
        self,
        script_id: str,
        title: str | None = None,
        raw_text: str | None = None,
        user_notes: str | None = None,
    ) -> Script | None:
        """Update a script's fields. Returns the updated script or None."""
        if not self.current_project:
            raise ValueError("No project loaded")
        for script in self.current_project.scripts:
            if script.id == script_id:
                if title is not None:
                    script.title = title
                if raw_text is not None:
                    script.raw_text = raw_text
                if user_notes is not None:
                    script.metadata.user_notes = user_notes
                self.save()
                self._notify_data()
                return script
        return None

    def save_script_analysis(self, script_id: str, result: dict) -> bool:
        """Save analysis result to a script. Returns True if saved."""
        if not self.current_project:
            return False
        for script in self.current_project.scripts:
            if script.id == script_id:
                script.analysis_result = result
                self.save()
                return True
        return False

    def remove_script(self, script_id: str) -> bool:
        """Remove a script by ID. Returns True if found and removed."""
        if not self.current_project:
            raise ValueError("No project loaded")
        original_len = len(self.current_project.scripts)
        self.current_project.scripts = [
            s for s in self.current_project.scripts if s.id != script_id
        ]
        if len(self.current_project.scripts) < original_len:
            self.save()
            self._notify_data()
            return True
        return False

    # --- Fact management ---

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
        if not self.current_project:
            raise ValueError("No project loaded")
        fact = Fact(
            character_id=character_id,
            location_id=location_id,
            time_slot=time_slot,
            source_type=source_type,
            source_evidence=source_evidence,
            source_script_ids=source_script_ids or [],
        )
        self.current_project.facts.append(fact)
        self.save()
        self._notify_data()
        return fact

    def remove_fact(self, fact_id: str) -> bool:
        """Remove a fact by ID. Returns True if found and removed."""
        if not self.current_project:
            raise ValueError("No project loaded")
        original_len = len(self.current_project.facts)
        self.current_project.facts = [
            f for f in self.current_project.facts if f.id != fact_id
        ]
        if len(self.current_project.facts) < original_len:
            self.save()
            self._notify_data()
            return True
        return False

    # --- Time slot management ---

    def add_time_slot(self, time_slot: str) -> bool:
        """Add a time slot. Validates HH:MM format. Returns True if added."""
        if not self.current_project:
            raise ValueError("No project loaded")
        if not re.match(r"^\d{2}:\d{2}$", time_slot):
            raise ValueError(f"时间格式必须为 HH:MM，收到: '{time_slot}'")
        if time_slot in self.current_project.time_slots:
            return False  # Already exists
        self.current_project.time_slots.append(time_slot)
        self.current_project.time_slots.sort()
        self.save()
        self._notify_data()
        return True

    def remove_time_slot(self, time_slot: str) -> bool:
        """Remove a time slot. Returns True if found and removed."""
        if not self.current_project:
            raise ValueError("No project loaded")
        if time_slot in self.current_project.time_slots:
            self.current_project.time_slots.remove(time_slot)
            self.save()
            self._notify_data()
            return True
        return False

    # --- Hint management ---

    def add_hint(
        self,
        hint_type: HintType,
        content: str,
    ) -> Hint:
        """Add a hint/rule/constraint to the current project."""
        if not self.current_project:
            raise ValueError("No project loaded")
        hint = Hint(type=hint_type, content=content)
        self.current_project.hints.append(hint)
        self.save()
        self._notify_data()
        return hint

    def remove_hint(self, hint_id: str) -> bool:
        """Remove a hint by ID. Returns True if found and removed."""
        if not self.current_project:
            raise ValueError("No project loaded")
        original_len = len(self.current_project.hints)
        self.current_project.hints = [
            h for h in self.current_project.hints if h.id != hint_id
        ]
        if len(self.current_project.hints) < original_len:
            self.save()
            self._notify_data()
            return True
        return False

    # --- Deduction management ---

    def add_deduction(self, deduction: Deduction) -> Deduction:
        """Add a pending deduction to the current project."""
        if not self.current_project:
            raise ValueError("No project loaded")
        self.current_project.deductions.append(deduction)
        self.save()
        self._notify_data()
        return deduction

    def accept_deduction(self, deduction_id: str) -> Fact | None:
        """Accept a deduction: create a Fact from it, mark it accepted.

        Returns the created Fact, or None if deduction not found.
        """
        if not self.current_project:
            raise ValueError("No project loaded")
        ded = next(
            (d for d in self.current_project.deductions if d.id == deduction_id),
            None,
        )
        if not ded:
            return None
        # Mark deduction as accepted
        ded.status = DeductionStatus.accepted
        ded.resolved_at = datetime.now()
        # Create a Fact from the deduction
        fact = Fact(
            character_id=ded.character_id,
            location_id=ded.location_id,
            time_slot=ded.time_slot,
            source_type=SourceType.ai_deduction,
            source_evidence=ded.reasoning,
            source_script_ids=ded.supporting_script_ids,
            from_deduction_id=ded.id,
        )
        self.current_project.facts.append(fact)
        self.save()
        self._notify_data()
        return fact

    def reject_deduction(self, deduction_id: str, reason: str = "") -> Rejection | None:
        """Reject a deduction: create a Rejection record, mark it rejected.

        Returns the created Rejection, or None if deduction not found.
        """
        if not self.current_project:
            raise ValueError("No project loaded")
        ded = next(
            (d for d in self.current_project.deductions if d.id == deduction_id),
            None,
        )
        if not ded:
            return None
        # Mark deduction as rejected
        ded.status = DeductionStatus.rejected
        ded.resolved_at = datetime.now()
        # Create a Rejection record
        rejection = Rejection(
            character_id=ded.character_id,
            location_id=ded.location_id,
            time_slot=ded.time_slot,
            reason=reason or "用户拒绝",
            from_deduction_id=ded.id,
        )
        self.current_project.rejections.append(rejection)
        self.save()
        self._notify_data()
        return rejection

    def get_pending_deductions(self) -> list[Deduction]:
        """Return list of pending deductions."""
        if not self.current_project:
            return []
        return [
            d for d in self.current_project.deductions
            if d.status == DeductionStatus.pending
        ]

    def clear_pending_deductions(self) -> int:
        """Remove all pending deductions. Returns count removed."""
        if not self.current_project:
            return 0
        original_len = len(self.current_project.deductions)
        self.current_project.deductions = [
            d for d in self.current_project.deductions
            if d.status != DeductionStatus.pending
        ]
        removed = original_len - len(self.current_project.deductions)
        if removed > 0:
            self.save()
            self._notify_data()
        return removed


# Module-level singleton instance
app_state = AppState()
