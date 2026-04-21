from __future__ import annotations

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
from src.storage.repository import Repository
from src.storage.sqlite_store import SQLiteStore


class SQLiteRepository(Repository):
    """SQLite-backed repository preserving JsonRepository caller-visible behavior."""

    def __init__(self, store: SQLiteStore | None = None) -> None:
        self.store = store or SQLiteStore()
        self.current_project: Project | None = None
        self._cache = CacheManager()

    def _require_project(self) -> Project:
        if self.current_project is None:
            raise ValueError("No project loaded")
        return self.current_project

    def _rebuild_indexes(self) -> None:
        if self.current_project is not None:
            self._cache.rebuild(self.current_project)
        else:
            self._cache = CacheManager()

    def _cascade_delete_referencing_records(
        self,
        match_fn: Callable[[Fact | Deduction | Rejection], bool],
    ) -> None:
        proj = self._require_project()

        removed_facts = [f for f in proj.facts if match_fn(f)]
        if removed_facts:
            proj.facts = [f for f in proj.facts if not match_fn(f)]
            for fact in removed_facts:
                self._cache.invalidate_fact("remove", fact)

        removed_deductions = [d for d in proj.deductions if match_fn(d)]
        if removed_deductions:
            proj.deductions = [d for d in proj.deductions if not match_fn(d)]
            for ded in removed_deductions:
                triple = (ded.character_id, ded.location_id, ded.time_slot)
                if ded.status == DeductionStatus.pending:
                    self._cache.pending_index.discard(triple)

        removed_rejections = [r for r in proj.rejections if match_fn(r)]
        if removed_rejections:
            proj.rejections = [r for r in proj.rejections if not match_fn(r)]
            for rej in removed_rejections:
                self._cache.invalidate_rejection("remove", rej)

    def load_project(self, project_id: str) -> None:
        self.current_project = self.store.load_project(project_id)
        self._rebuild_indexes()
        logger.info(
            "SQLiteRepository.load_project: loaded {!r} (id={})",
            self.current_project.name,
            project_id,
        )

    def save(self) -> None:
        if self.current_project:
            self.current_project.updated_at = datetime.now()
            self.store.save_project(self.current_project)

    def create_project(
        self,
        name: str,
        description: str | None = None,
        time_slots: list[str] | None = None,
    ) -> Project:
        project = self.store.create_project(
            name=name,
            description=description,
            time_slots=time_slots or [],
        )
        self.current_project = project
        self._rebuild_indexes()
        logger.info("SQLiteRepository.create_project: created {!r} (id={})", name, project.id)
        return project

    def delete_project(self, project_id: str) -> None:
        self.store.delete_project(project_id)
        if self.current_project and self.current_project.id == project_id:
            self.current_project = None
            self._cache = CacheManager()
        logger.info("SQLiteRepository.delete_project: deleted id={!r}", project_id)

    def list_projects(self) -> list[ProjectSummary]:
        return self.store.list_projects()

    def add_character(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus = CharacterStatus.confirmed,
    ) -> Character:
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
        return char

    def update_character(
        self,
        character_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
        status: CharacterStatus | None = None,
    ) -> Character | None:
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
                self._cache.invalidate_character(
                    "update", char, old_name=old_name, remaining_characters=proj.characters
                )
                self.save()
                return char
        return None

    def remove_character(self, character_id: str) -> bool:
        proj = self._require_project()
        char = next((c for c in proj.characters if c.id == character_id), None)
        if char is None:
            return False

        char_name = char.name
        proj.characters = [c for c in proj.characters if c.id != character_id]
        self._cache.invalidate_character("remove", char, remaining_characters=proj.characters)
        self._cascade_delete_referencing_records(lambda r: r.character_id == character_id)

        for script in proj.scripts:
            if char_name in script.metadata.characters_mentioned:
                script.metadata.characters_mentioned = [
                    name for name in script.metadata.characters_mentioned if name != char_name
                ]

        self.save()
        return True

    def add_location(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location:
        proj = self._require_project()
        loc = Location(name=name, aliases=aliases or [], description=description)
        proj.locations.append(loc)
        self._cache.invalidate_location("add", loc)
        self.save()
        return loc

    def update_location(
        self,
        location_id: str,
        name: str | None = None,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> Location | None:
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
                self._cache.invalidate_location(
                    "update", loc, old_name=old_name, remaining_locations=proj.locations
                )
                self.save()
                return loc
        return None

    def remove_location(self, location_id: str) -> bool:
        proj = self._require_project()
        loc = next((lo for lo in proj.locations if lo.id == location_id), None)
        if loc is None:
            return False

        proj.locations = [lo for lo in proj.locations if lo.id != location_id]
        self._cache.invalidate_location("remove", loc, remaining_locations=proj.locations)
        self._cascade_delete_referencing_records(lambda r: r.location_id == location_id)
        self.save()
        return True

    def add_script(
        self,
        raw_text: str,
        title: str | None = None,
        user_notes: str | None = None,
        stated_time: str | None = None,
        stated_location: str | None = None,
    ) -> Script:
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
        if not self.current_project:
            return False
        for script in self.current_project.scripts:
            if script.id == script_id:
                script.analysis_result = result
                self.save()
                return True
        return False

    def remove_script(self, script_id: str) -> bool:
        proj = self._require_project()
        original_len = len(proj.scripts)
        proj.scripts = [s for s in proj.scripts if s.id != script_id]
        if len(proj.scripts) < original_len:
            for fact in proj.facts:
                if script_id in fact.source_script_ids:
                    fact.source_script_ids = [sid for sid in fact.source_script_ids if sid != script_id]
            for ded in proj.deductions:
                if script_id in ded.supporting_script_ids:
                    ded.supporting_script_ids = [
                        sid for sid in ded.supporting_script_ids if sid != script_id
                    ]
            self.save()
            return True
        return False

    def add_fact(
        self,
        character_id: str,
        location_id: str,
        time_slot: str,
        source_type: SourceType = SourceType.user_input,
        source_evidence: str | None = None,
        source_script_ids: list[str] | None = None,
    ) -> Fact:
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
        proj = self._require_project()
        for fact in proj.facts:
            if fact.id == fact_id:
                proj.facts = [f for f in proj.facts if f.id != fact_id]
                self._cache.invalidate_fact("remove", fact)
                self.save()
                return True
        return False

    def add_time_slot(self, time_slot: str, description: str = "") -> TimeSlot | None:
        import re

        proj = self._require_project()
        if not re.match(r"^\d{2}:\d{2}$", time_slot):
            raise ValueError(f"Time slot label must be HH:MM format, got {time_slot!r}")
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
        proj = self._require_project()
        ts = next((t for t in proj.time_slots if t.id == time_slot_id), None)
        if ts is None:
            return False

        proj.time_slots = [t for t in proj.time_slots if t.id != time_slot_id]
        self._cache.invalidate_time_slot("remove", ts)
        self._cascade_delete_referencing_records(lambda r: r.time_slot == time_slot_id)
        self.save()
        return True

    def reorder_time_slot(self, time_slot_id: str, direction: int) -> bool:
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
        if not self.current_project:
            return None
        return self._cache.ts_by_id.get(ts_id)

    def get_time_slot_label(self, ts_id: str) -> str:
        ts = self.get_time_slot_by_id(ts_id)
        if ts is None:
            return ts_id
        if ts.description:
            return f"{ts.label} ({ts.description})"
        return ts.label

    def add_hint(self, hint_type: HintType, content: str) -> Hint:
        proj = self._require_project()
        hint = Hint(type=hint_type, content=content)
        proj.hints.append(hint)
        self.save()
        return hint

    def update_hint(
        self,
        hint_id: str,
        hint_type: HintType | None = None,
        content: str | None = None,
    ) -> bool:
        proj = self._require_project()
        for hint in proj.hints:
            if hint.id == hint_id:
                if hint_type is not None:
                    hint.type = hint_type
                if content is not None:
                    hint.content = content
                self.save()
                return True
        return False

    def remove_hint(self, hint_id: str) -> bool:
        proj = self._require_project()
        original_len = len(proj.hints)
        proj.hints = [h for h in proj.hints if h.id != hint_id]
        if len(proj.hints) < original_len:
            self.save()
            return True
        return False

    def ignore_entity(self, kind: EntityKind, name: str) -> IgnoredEntity:
        proj = self._require_project()
        name = name.strip()
        for entry in proj.ignored_entities:
            if entry.kind == kind and entry.name.lower() == name.lower():
                return entry
        entry = IgnoredEntity(kind=kind, name=name)
        proj.ignored_entities.append(entry)
        self.save()
        return entry

    def is_entity_ignored(self, kind: EntityKind, name: str) -> bool:
        if not self.current_project:
            return False
        name_lower = name.strip().lower()
        return any(
            entry.kind == kind and entry.name.lower() == name_lower
            for entry in self.current_project.ignored_entities
        )

    def merge_character(self, source_name: str, target_id: str) -> Character | None:
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

    def add_deduction(self, deduction: Deduction) -> bool:
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
            reason=reason or "用户拒绝",
            from_deduction_id=ded.id,
        )
        proj.rejections.append(rejection)
        self._cache.invalidate_deduction("reject", ded, rejection=rejection)
        self.save()
        return rejection

    def get_pending_deductions(self) -> list[Deduction]:
        if not self.current_project:
            return []
        return [d for d in self.current_project.deductions if d.status == DeductionStatus.pending]

    def clear_pending_deductions(self) -> int:
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
