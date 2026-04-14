from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from loguru import logger

from src.models.puzzle import (
    Character,
    CharacterStatus,
    Deduction,
    DeductionStatus,
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
    ScriptMetadata,
    SourceType,
    TimeSlot,
)
from src.storage.cache_manager import CacheManager
from src.storage.json_store import JsonStore


class JsonRepository:
    """JsonRepository implements the Repository Protocol.

    Wraps JsonStore for disk I/O and CacheManager for in-memory indexes.
    Every mutation: update project -> invalidate cache -> save to disk.
    """

    def __init__(self, store: JsonStore | None = None) -> None:
        self.store = store or JsonStore()
        self.current_project: Project | None = None
        self._cache = CacheManager()

    def _require_project(self) -> Project:
        """Raise ValueError if no project is loaded."""
        if self.current_project is None:
            raise ValueError("No project loaded")
        return self.current_project

    def _rebuild_indexes(self) -> None:
        """Rebuild all cache indexes from current project data."""
        if self.current_project is not None:
            self._cache.rebuild(self.current_project)
        else:
            self._cache = CacheManager()

    def _cascade_delete_referencing_records(
        self,
        match_fn: Callable[[Fact | Deduction | Rejection], bool],
    ) -> None:
        """Remove all facts, deductions, and rejections that match the predicate.

        Also updates the 3 dedup indexes (fact_index, pending_index,
        rejection_index) to remove stale triples, and cleans the
        rejection_map for any removed rejections.
        """
        proj = self._require_project()

        # Cascade facts
        removed_facts = [f for f in proj.facts if match_fn(f)]
        if removed_facts:
            proj.facts = [f for f in proj.facts if not match_fn(f)]
            for fact in removed_facts:
                self._cache.invalidate_fact("remove", fact)

        # Cascade deductions (all statuses: pending, accepted, rejected)
        removed_deductions = [d for d in proj.deductions if match_fn(d)]
        if removed_deductions:
            proj.deductions = [d for d in proj.deductions if not match_fn(d)]
            for ded in removed_deductions:
                triple = (ded.character_id, ded.location_id, ded.time_slot)
                if ded.status == DeductionStatus.pending:
                    self._cache.pending_index.discard(triple)

        # Cascade rejections
        removed_rejections = [r for r in proj.rejections if match_fn(r)]
        if removed_rejections:
            proj.rejections = [r for r in proj.rejections if not match_fn(r)]
            for rej in removed_rejections:
                self._cache.invalidate_rejection("remove", rej)

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def load_project(self, project_id: str) -> None:
        """Load a project by ID and set it as the current project."""
        self.current_project = self.store.load_project(project_id)
        self._rebuild_indexes()
        logger.info(
            "JsonRepository.load_project: loaded {!r} (id={})",
            self.current_project.name,
            project_id,
        )

    def save(self) -> None:
        """Save the current project to disk (bumps updated_at)."""
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
        logger.info("JsonRepository.create_project: created {!r} (id={})", name, project.id)
        return project

    def delete_project(self, project_id: str) -> None:
        """Delete a project. If it is the current project, unset it."""
        self.store.delete_project(project_id)
        if self.current_project and self.current_project.id == project_id:
            self.current_project = None
            self._cache = CacheManager()
        logger.info("JsonRepository.delete_project: deleted id={!r}", project_id)

    def list_projects(self) -> list[ProjectSummary]:
        """List all available projects as summaries."""
        return self.store.list_projects()

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
        proj = self._require_project()
        char = Character(
            name=name,
            aliases=aliases or [],
            description=description,
            status=status,
        )
        proj.characters.append(char)
        self._cache.invalidate_character("add", char)
        self.save()
        logger.info("JsonRepository.add_character: added {!r} (id={})", name, char.id)
        return char

    def update_character(
        self,
        character_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus | None = None,
    ) -> Character | None:
        """Update a character fields. Returns updated character or None."""
        proj = self._require_project()
        for char in proj.characters:
            if char.id == character_id:
                old_name = char.name
                if name is not None:
                    char.name = name
                if aliases is not None:
                    char.aliases = aliases
                if description is not None:
                    char.description = description
                if status is not None:
                    char.status = status
                self._cache.invalidate_character("update", char, old_name=old_name)
                self.save()
                return char
        return None

    def remove_character(self, character_id: str) -> bool:
        """Remove a character by ID with cascade delete.

        Cascades: deletes all Facts, Deductions, and Rejections referencing
        this character_id. Also removes the character's name from every
        Script.metadata.characters_mentioned list.
        """
        proj = self._require_project()
        char = next((c for c in proj.characters if c.id == character_id), None)
        if char is None:
            return False

        char_name = char.name

        # Remove the character entity
        proj.characters = [c for c in proj.characters if c.id != character_id]
        self._cache.invalidate_character("remove", char)

        # Cascade: remove referencing facts, deductions, rejections
        self._cascade_delete_referencing_records(
            lambda r: r.character_id == character_id,
        )

        # Cascade: clean Script.metadata.characters_mentioned
        for script in proj.scripts:
            if char_name in script.metadata.characters_mentioned:
                script.metadata.characters_mentioned = [
                    n for n in script.metadata.characters_mentioned if n != char_name
                ]

        self.save()
        return True

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
        proj = self._require_project()
        loc = Location(
            name=name,
            aliases=aliases or [],
            description=description,
        )
        proj.locations.append(loc)
        self._cache.invalidate_location("add", loc)
        self.save()
        logger.info("JsonRepository.add_location: added {!r} (id={})", name, loc.id)
        return loc

    def update_location(
        self,
        location_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location | None:
        """Update a location fields. Returns updated location or None."""
        proj = self._require_project()
        for loc in proj.locations:
            if loc.id == location_id:
                old_name = loc.name
                if name is not None:
                    loc.name = name
                if aliases is not None:
                    loc.aliases = aliases
                if description is not None:
                    loc.description = description
                self._cache.invalidate_location("update", loc, old_name=old_name)
                self.save()
                return loc
        return None

    def remove_location(self, location_id: str) -> bool:
        """Remove a location by ID with cascade delete.

        Cascades: deletes all Facts, Deductions, and Rejections referencing
        this location_id.
        """
        proj = self._require_project()
        loc = next((lo for lo in proj.locations if lo.id == location_id), None)
        if loc is None:
            return False

        proj.locations = [lo for lo in proj.locations if lo.id != location_id]
        self._cache.invalidate_location("remove", loc)

        # Cascade: remove referencing facts, deductions, rejections
        self._cascade_delete_referencing_records(
            lambda r: r.location_id == location_id,
        )

        self.save()
        return True

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
        proj = self._require_project()
        metadata = ScriptMetadata(
            stated_time=stated_time,
            stated_location=stated_location,
            user_notes=user_notes,
            source_order=len(proj.scripts) + 1,
        )
        script = Script(title=title, raw_text=raw_text, metadata=metadata)
        proj.scripts.append(script)
        self.save()
        return script

    def update_script(
        self,
        script_id: str,
        title: str | None = None,
        raw_text: str | None = None,
        user_notes: str | None = None,
    ) -> Script | None:
        """Update a script fields. Returns updated script or None."""
        proj = self._require_project()
        for script in proj.scripts:
            if script.id == script_id:
                if title is not None:
                    script.title = title
                if raw_text is not None:
                    script.raw_text = raw_text
                if user_notes is not None:
                    script.metadata.user_notes = user_notes
                self.save()
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
        """Remove a script by ID with cascade cleanup.

        Cascades: removes this script's ID from every Fact.source_script_ids
        and every Deduction.supporting_script_ids. The facts and deductions
        themselves are NOT deleted.
        """
        proj = self._require_project()
        original_len = len(proj.scripts)
        proj.scripts = [s for s in proj.scripts if s.id != script_id]
        if len(proj.scripts) < original_len:
            # Cascade: clean script ID from fact source_script_ids
            for fact in proj.facts:
                if script_id in fact.source_script_ids:
                    fact.source_script_ids = [
                        sid for sid in fact.source_script_ids if sid != script_id
                    ]
            # Cascade: clean script ID from deduction supporting_script_ids
            for ded in proj.deductions:
                if script_id in ded.supporting_script_ids:
                    ded.supporting_script_ids = [
                        sid for sid in ded.supporting_script_ids if sid != script_id
                    ]
            self.save()
            return True
        return False

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
        proj = self._require_project()
        fact = Fact(
            character_id=character_id,
            location_id=location_id,
            time_slot=time_slot,
            source_type=source_type,
            source_evidence=source_evidence,
            source_script_ids=source_script_ids or [],
        )
        proj.facts.append(fact)
        self._cache.invalidate_fact("add", fact)
        self.save()
        return fact

    def remove_fact(self, fact_id: str) -> bool:
        """Remove a fact by ID. Returns True if found and removed."""
        proj = self._require_project()
        for fact in proj.facts:
            if fact.id == fact_id:
                proj.facts = [f for f in proj.facts if f.id != fact_id]
                self._cache.invalidate_fact("remove", fact)
                self.save()
                return True
        return False

    # ------------------------------------------------------------------
    # Time slot management
    # ------------------------------------------------------------------

    def add_time_slot(self, time_slot: str, description: str = "") -> TimeSlot | None:
        """Add a time slot. Validates HH:MM format. Returns TimeSlot if added, None if duplicate."""
        proj = self._require_project()
        if not re.match(r"^\d{2}:\d{2}$", time_slot):
            raise ValueError(f"Time slot label must be HH:MM format, got {time_slot!r}")
        # Dedup by (label, description)
        for ts in proj.time_slots:
            if ts.label == time_slot and ts.description == description:
                return None
        max_order = max((ts.sort_order for ts in proj.time_slots), default=-1)
        new_ts = TimeSlot(label=time_slot, description=description, sort_order=max_order + 1)
        proj.time_slots.append(new_ts)
        proj.time_slots.sort(key=lambda ts: ts.sort_order)
        self._cache.invalidate_time_slot("add", new_ts)
        self.save()
        return new_ts

    def remove_time_slot(self, time_slot_id: str) -> bool:
        """Remove a time slot by ID with cascade delete.

        Cascades: deletes all Facts, Deductions, and Rejections referencing
        this time_slot ID.
        """
        proj = self._require_project()
        ts = next((t for t in proj.time_slots if t.id == time_slot_id), None)
        if ts is None:
            return False

        proj.time_slots = [t for t in proj.time_slots if t.id != time_slot_id]
        self._cache.invalidate_time_slot("remove", ts)

        # Cascade: remove referencing facts, deductions, rejections
        self._cascade_delete_referencing_records(
            lambda r: r.time_slot == time_slot_id,
        )

        self.save()
        return True

    def reorder_time_slot(self, time_slot_id: str, direction: int) -> bool:
        """Move a time slot up (direction=-1) or down (direction=1) in sort order."""
        proj = self._require_project()
        slots = sorted(proj.time_slots, key=lambda ts: ts.sort_order)
        idx = next((i for i, ts in enumerate(slots) if ts.id == time_slot_id), None)
        if idx is None:
            return False
        swap_idx = idx + direction
        if swap_idx < 0 or swap_idx >= len(slots):
            return False
        slots[idx].sort_order, slots[swap_idx].sort_order = (
            slots[swap_idx].sort_order,
            slots[idx].sort_order,
        )
        proj.time_slots.sort(key=lambda ts: ts.sort_order)
        self.save()
        return True

    def get_time_slot_by_id(self, ts_id: str) -> TimeSlot | None:
        """Look up a time slot by ID. Returns None if not found."""
        if not self.current_project:
            return None
        return self._cache.ts_by_id.get(ts_id)

    def get_time_slot_label(self, ts_id: str) -> str:
        """Return display label for a time slot ID. Falls back to raw ID if not found."""
        ts = self.get_time_slot_by_id(ts_id)
        if ts is None:
            return ts_id
        if ts.description:
            return f"{ts.label} ({ts.description})"
        return ts.label

    # ------------------------------------------------------------------
    # Hint management
    # ------------------------------------------------------------------

    def add_hint(self, hint_type: HintType, content: str) -> Hint:
        """Add a hint/rule/constraint to the current project."""
        proj = self._require_project()
        hint = Hint(type=hint_type, content=content)
        proj.hints.append(hint)
        self.save()
        return hint

    def remove_hint(self, hint_id: str) -> bool:
        """Remove a hint by ID. Returns True if found and removed."""
        proj = self._require_project()
        original_len = len(proj.hints)
        proj.hints = [h for h in proj.hints if h.id != hint_id]
        if len(proj.hints) < original_len:
            self.save()
            return True
        return False

    # ------------------------------------------------------------------
    # Ignored entity management
    # ------------------------------------------------------------------

    def ignore_entity(self, kind: EntityKind, name: str) -> IgnoredEntity:
        """Permanently ignore a raw entity name."""
        proj = self._require_project()
        name = name.strip()
        for ie in proj.ignored_entities:
            if ie.kind == kind and ie.name.lower() == name.lower():
                return ie
        entry = IgnoredEntity(kind=kind, name=name)
        proj.ignored_entities.append(entry)
        self.save()
        return entry

    def is_entity_ignored(self, kind: EntityKind, name: str) -> bool:
        """Return True if this raw name has been ignored for the given kind."""
        if not self.current_project:
            return False
        name_lower = name.strip().lower()
        return any(
            ie.kind == kind and ie.name.lower() == name_lower
            for ie in self.current_project.ignored_entities
        )

    # ------------------------------------------------------------------
    # Entity merge
    # ------------------------------------------------------------------

    def merge_character(self, source_name: str, target_id: str) -> Character | None:
        """Merge source_name into existing character by adding it as alias."""
        proj = self._require_project()
        target = next((c for c in proj.characters if c.id == target_id), None)
        if not target:
            return None
        source_name = source_name.strip()
        if source_name.lower() != target.name.lower() and source_name not in target.aliases:
            target.aliases.append(source_name)
        self._cache.invalidate_character("update", target, old_name=target.name)
        self.save()
        return target

    def merge_location(self, source_name: str, target_id: str) -> Location | None:
        """Merge source_name into existing location by adding it as alias."""
        proj = self._require_project()
        target = next((lo for lo in proj.locations if lo.id == target_id), None)
        if not target:
            return None
        source_name = source_name.strip()
        if source_name.lower() != target.name.lower() and source_name not in target.aliases:
            target.aliases.append(source_name)
        self._cache.invalidate_location("update", target, old_name=target.name)
        self.save()
        return target

    # ------------------------------------------------------------------
    # Deduction management
    # ------------------------------------------------------------------

    def add_deduction(self, deduction: Deduction) -> bool:
        """Add a pending deduction. Returns True if added, False if duplicate."""
        proj = self._require_project()
        triple = (deduction.character_id, deduction.location_id, deduction.time_slot)
        if (
            triple in self._cache.fact_index
            or triple in self._cache.pending_index
            or triple in self._cache.rejection_index
        ):
            return False
        proj.deductions.append(deduction)
        self._cache.invalidate_deduction("add", deduction)
        self.save()
        return True

    def accept_deduction(self, deduction_id: str) -> Fact | None:
        """Accept a deduction: create a Fact from it, mark it accepted."""
        proj = self._require_project()
        ded = next((d for d in proj.deductions if d.id == deduction_id), None)
        if not ded:
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
        proj.facts.append(fact)
        self._cache.invalidate_deduction("accept", ded, fact=fact)
        self.save()
        return fact

    def reject_deduction(self, deduction_id: str, reason: str = "") -> Rejection | None:
        """Reject a deduction: create a Rejection record, mark it rejected."""
        proj = self._require_project()
        ded = next((d for d in proj.deductions if d.id == deduction_id), None)
        if not ded:
            return None
        ded.status = DeductionStatus.rejected
        ded.resolved_at = datetime.now()
        rejection = Rejection(
            character_id=ded.character_id,
            location_id=ded.location_id,
            time_slot=ded.time_slot,
            reason=reason or "\u7528\u6237\u62d2\u7edd",
            from_deduction_id=ded.id,
        )
        proj.rejections.append(rejection)
        self._cache.invalidate_deduction("reject", ded, rejection=rejection)
        self.save()
        return rejection

    def get_pending_deductions(self) -> list[Deduction]:
        """Return list of pending deductions."""
        if not self.current_project:
            return []
        return [d for d in self.current_project.deductions if d.status == DeductionStatus.pending]

    def clear_pending_deductions(self) -> int:
        """Remove all pending deductions. Returns count removed."""
        if not self.current_project:
            return 0
        original_len = len(self.current_project.deductions)
        self.current_project.deductions = [
            d for d in self.current_project.deductions if d.status != DeductionStatus.pending
        ]
        removed = original_len - len(self.current_project.deductions)
        if removed > 0:
            self._cache.invalidate_deduction("clear_pending", None)
            self.save()
        return removed
