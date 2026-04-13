"""App state management — singleton that holds the current project.

All UI mutations go through AppState methods which handle persistence.
The Flet UI layer will call page.update() directly after state changes.
"""

import re
from datetime import datetime
from typing import Optional

from loguru import logger

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
    """Manages the currently loaded project and provides state access."""

    def __init__(self, store: JsonStore | None = None):
        self.store = store or JsonStore()
        self.current_project: Optional[Project] = None
        # Deduplication indexes: O(1) lookup for (character_id, location_id, time_slot) triples
        self._fact_index: set[tuple[str, str, str]] = set()
        self._pending_index: set[tuple[str, str, str]] = set()
        self._rejection_index: set[tuple[str, str, str]] = set()

    def _rebuild_indexes(self) -> None:
        """Rebuild all three deduplication indexes from current project data."""
        self._fact_index = set()
        self._pending_index = set()
        self._rejection_index = set()
        if not self.current_project:
            return
        for f in self.current_project.facts:
            self._fact_index.add((f.character_id, f.location_id, f.time_slot))
        for d in self.current_project.deductions:
            if d.status == DeductionStatus.pending:
                self._pending_index.add((d.character_id, d.location_id, d.time_slot))
        for r in self.current_project.rejections:
            self._rejection_index.add((r.character_id, r.location_id, r.time_slot))

    # --- Project management ---

    def load_project(self, project_id: str) -> None:
        """Load a project by ID and set it as the current project."""
        self.current_project = self.store.load_project(project_id)
        self._rebuild_indexes()
        logger.info("AppState.load_project: loaded {!r} (id={})", self.current_project.name, project_id)

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
        self._rebuild_indexes()
        logger.info("AppState.create_project: created {!r} (id={})", name, project.id)
        return project

    def delete_project(self, project_id: str) -> None:
        """Delete a project. If it's the current project, unset it."""
        self.store.delete_project(project_id)
        if self.current_project and self.current_project.id == project_id:
            self.current_project = None
        logger.info("AppState.delete_project: deleted id={!r}", project_id)

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
        logger.info("AppState.add_character: added {!r} (id={})", name, char.id)
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
                logger.info("AppState.update_character: updated id={!r} name={!r}", character_id, char.name)
                return char
        logger.warning("AppState.update_character: id={!r} not found", character_id)
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
            logger.info("AppState.remove_character: removed id={!r}", character_id)
            return True
        logger.warning("AppState.remove_character: id={!r} not found", character_id)
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
        logger.info("AppState.add_location: added {!r} (id={})", name, loc.id)
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
                logger.info("AppState.update_location: updated id={!r} name={!r}", location_id, loc.name)
                return loc
        logger.warning("AppState.update_location: id={!r} not found", location_id)
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
            logger.info("AppState.remove_location: removed id={!r}", location_id)
            return True
        logger.warning("AppState.remove_location: id={!r} not found", location_id)
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
        logger.info(
            "AppState.add_script: added {!r} (id={}) len={}",
            title or "Untitled", script.id, len(raw_text),
        )
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
                logger.info("AppState.update_script: updated id={!r}", script_id)
                return script
        logger.warning("AppState.update_script: id={!r} not found", script_id)
        return None

    def save_script_analysis(self, script_id: str, result: dict) -> bool:
        """Save analysis result to a script. Returns True if saved."""
        if not self.current_project:
            return False
        for script in self.current_project.scripts:
            if script.id == script_id:
                script.analysis_result = result
                self.save()
                logger.info("AppState.save_script_analysis: saved for id={!r}", script_id)
                return True
        logger.warning("AppState.save_script_analysis: script id={!r} not found", script_id)
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
            logger.info("AppState.remove_script: removed id={!r}", script_id)
            return True
        logger.warning("AppState.remove_script: id={!r} not found", script_id)
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
        self._fact_index.add((character_id, location_id, time_slot))
        self.save()
        logger.info(
            "AppState.add_fact: char={!r} loc={!r} ts={!r} source={}",
            character_id, location_id, time_slot, source_type,
        )
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
            logger.info("AppState.remove_fact: removed id={!r}", fact_id)
            return True
        logger.warning("AppState.remove_fact: id={!r} not found", fact_id)
        return False

    # --- Time slot management ---

    def add_time_slot(self, time_slot: str) -> bool:
        """Add a time slot. Validates HH:MM format. Returns True if added."""
        if not self.current_project:
            raise ValueError("No project loaded")
        if not re.match(r"^\d{2}:\d{2}$", time_slot):
            raise ValueError(f"时间格式必须为 HH:MM，收到: '{time_slot}'")
        if time_slot in self.current_project.time_slots:
            logger.debug("AppState.add_time_slot: {!r} already exists, skipped", time_slot)
            return False
        self.current_project.time_slots.append(time_slot)
        self.current_project.time_slots.sort()
        self.save()
        logger.info("AppState.add_time_slot: added {!r}", time_slot)
        return True

    def remove_time_slot(self, time_slot: str) -> bool:
        """Remove a time slot. Returns True if found and removed."""
        if not self.current_project:
            raise ValueError("No project loaded")
        if time_slot in self.current_project.time_slots:
            self.current_project.time_slots.remove(time_slot)
            self.save()
            logger.info("AppState.remove_time_slot: removed {!r}", time_slot)
            return True
        logger.warning("AppState.remove_time_slot: {!r} not found", time_slot)
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
        logger.info("AppState.add_hint: type={} content={!r:.60}", hint_type, content)
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
            logger.info("AppState.remove_hint: removed id={!r}", hint_id)
            return True
        logger.warning("AppState.remove_hint: id={!r} not found", hint_id)
        return False

    # --- Deduction management ---

    def add_deduction(self, deduction: Deduction) -> bool:
        """Add a pending deduction to the current project.

        Checks if the (character_id, location_id, time_slot) triple already exists
        as a confirmed Fact, pending Deduction, or Rejection. If so, silently skips.

        Returns:
            True if the deduction was added, False if it was skipped as a duplicate.
        """
        if not self.current_project:
            raise ValueError("No project loaded")
        triple = (deduction.character_id, deduction.location_id, deduction.time_slot)
        # Check all three indexes for duplicates
        if triple in self._fact_index or triple in self._pending_index or triple in self._rejection_index:
            logger.debug(
                "AppState.add_deduction: skipping duplicate char={!r} loc={!r} ts={!r}",
                deduction.character_id, deduction.location_id, deduction.time_slot,
            )
            return False
        self.current_project.deductions.append(deduction)
        self._pending_index.add(triple)
        self.save()
        logger.debug(
            "AppState.add_deduction: char={!r} loc={!r} ts={!r} conf={}",
            deduction.character_id, deduction.location_id,
            deduction.time_slot, deduction.confidence,
        )
        return True

    def accept_deduction(self, deduction_id: str) -> Fact | None:
        """Accept a deduction: create a Fact from it, mark it accepted."""
        if not self.current_project:
            raise ValueError("No project loaded")
        ded = next(
            (d for d in self.current_project.deductions if d.id == deduction_id),
            None,
        )
        if not ded:
            logger.warning("AppState.accept_deduction: id={!r} not found", deduction_id)
            return None
        ded.status = DeductionStatus.accepted
        ded.resolved_at = datetime.now()
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
        # Update indexes: remove from pending, add to fact
        triple = (ded.character_id, ded.location_id, ded.time_slot)
        self._pending_index.discard(triple)
        self._fact_index.add(triple)
        self.save()
        logger.info(
            "AppState.accept_deduction: id={!r} → fact char={!r} loc={!r} ts={!r}",
            deduction_id, ded.character_id, ded.location_id, ded.time_slot,
        )
        return fact

    def reject_deduction(self, deduction_id: str, reason: str = "") -> Rejection | None:
        """Reject a deduction: create a Rejection record, mark it rejected."""
        if not self.current_project:
            raise ValueError("No project loaded")
        ded = next(
            (d for d in self.current_project.deductions if d.id == deduction_id),
            None,
        )
        if not ded:
            logger.warning("AppState.reject_deduction: id={!r} not found", deduction_id)
            return None
        ded.status = DeductionStatus.rejected
        ded.resolved_at = datetime.now()
        rejection = Rejection(
            character_id=ded.character_id,
            location_id=ded.location_id,
            time_slot=ded.time_slot,
            reason=reason or "用户拒绝",
            from_deduction_id=ded.id,
        )
        self.current_project.rejections.append(rejection)
        # Update indexes: remove from pending, add to rejection
        triple = (ded.character_id, ded.location_id, ded.time_slot)
        self._pending_index.discard(triple)
        self._rejection_index.add(triple)
        self.save()
        logger.info(
            "AppState.reject_deduction: id={!r} reason={!r:.60}",
            deduction_id, reason,
        )
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
            self._pending_index.clear()
            self.save()
            logger.info("AppState.clear_pending_deductions: removed {}", removed)
        return removed


# Module-level singleton instance
app_state = AppState()
