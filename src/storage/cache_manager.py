"""CacheManager — centralized in-memory lookup indexes for a Project.

Replaces the 7+ ad-hoc maps scattered across UI pages with a single,
coherent index layer that is rebuilt once on project load and then
surgically updated on every mutation.

All indexes are O(1) lookups. CacheManager is framework-agnostic (no flet imports).
"""

from __future__ import annotations

from src.models.puzzle import (
    Character,
    Deduction,
    DeductionStatus,
    Fact,
    Location,
    Project,
    Rejection,
    TimeSlot,
)


class CacheManager:
    """Centralized lookup indexes for a Project.

    Indexes
    -------
    char_by_id      : {char.id: Character}
    loc_by_id       : {loc.id: Location}
    ts_by_id        : {ts.id: TimeSlot}
    char_by_name    : {char.name.lower(): Character}  (last-writer-wins for dupes)
    loc_by_name     : {loc.name.lower(): Location}    (last-writer-wins for dupes)
    ts_label_map    : {"HH:MM(desc)": ts_id, "HH:MM": ts_id}
                      full key always written; bare key only if not already present
                      (first-writer-wins for bare label conflicts)
    rejection_map   : {from_deduction_id: reason}  (None keys excluded)
    fact_index      : set of (char_id, loc_id, ts_id) from confirmed facts
    pending_index   : set of (char_id, loc_id, ts_id) from pending deductions
    rejection_index : set of (char_id, loc_id, ts_id) from rejections
    """

    def __init__(self) -> None:
        self.char_by_id: dict[str, Character] = {}
        self.loc_by_id: dict[str, Location] = {}
        self.ts_by_id: dict[str, TimeSlot] = {}
        self.char_by_name: dict[str, Character] = {}
        self.loc_by_name: dict[str, Location] = {}
        self.ts_label_map: dict[str, str] = {}
        self.rejection_map: dict[str, str] = {}
        self.fact_index: set[tuple[str, str, str]] = set()
        self.pending_index: set[tuple[str, str, str]] = set()
        self.rejection_index: set[tuple[str, str, str]] = set()

    # ------------------------------------------------------------------
    # Full rebuild
    # ------------------------------------------------------------------

    def rebuild(self, project: Project) -> None:
        """Reconstruct all indexes from scratch using current project data.

        This is the single point for full rebuild — called once on project load.
        """
        # Entity-by-id and by-name indexes
        self.char_by_id = {c.id: c for c in project.characters}
        self.loc_by_id = {loc.id: loc for loc in project.locations}
        self.ts_by_id = {ts.id: ts for ts in project.time_slots}

        # Case-insensitive by-name (last-writer-wins for duplicates)
        self.char_by_name = {c.name.lower(): c for c in project.characters}
        self.loc_by_name = {loc.name.lower(): loc for loc in project.locations}

        # ts_label_map: full key + bare label (first-writer-wins for bare conflicts)
        self.ts_label_map = {}
        for ts in project.time_slots:
            self._index_ts_add(ts)

        # rejection_map: from_deduction_id → reason (excluding None keys)
        self.rejection_map = {}
        for rej in project.rejections:
            if rej.from_deduction_id is not None:
                self.rejection_map[rej.from_deduction_id] = rej.reason

        # Triple dedup indexes
        self.fact_index = {(f.character_id, f.location_id, f.time_slot) for f in project.facts}
        self.pending_index = {
            (d.character_id, d.location_id, d.time_slot)
            for d in project.deductions
            if d.status == DeductionStatus.pending
        }
        self.rejection_index = {
            (r.character_id, r.location_id, r.time_slot) for r in project.rejections
        }

    # ------------------------------------------------------------------
    # Targeted invalidation helpers
    # ------------------------------------------------------------------

    def invalidate_character(
        self,
        action: str,
        char: Character | None,
        *,
        old_name: str | None = None,
    ) -> None:
        """Update char_by_id and char_by_name after a character mutation.

        Parameters
        ----------
        action   : "add" | "remove" | "update"
        char     : the character being mutated (current state)
        old_name : the previous name (only needed for "update")
        """
        if char is None:
            return
        if action == "add":
            self.char_by_id[char.id] = char
            self.char_by_name[char.name.lower()] = char
        elif action == "remove":
            self.char_by_id.pop(char.id, None)
            # Only remove from by-name if this is the current value
            key = char.name.lower()
            if self.char_by_name.get(key) is char:
                del self.char_by_name[key]
        elif action == "update":
            self.char_by_id[char.id] = char
            # Remove old name entry if it points to this char
            if old_name is not None:
                old_key = old_name.lower()
                if self.char_by_name.get(old_key) is char:
                    del self.char_by_name[old_key]
            self.char_by_name[char.name.lower()] = char

    def invalidate_location(
        self,
        action: str,
        loc: Location | None,
        *,
        old_name: str | None = None,
    ) -> None:
        """Update loc_by_id and loc_by_name after a location mutation.

        Parameters
        ----------
        action   : "add" | "remove" | "update"
        loc      : the location being mutated (current state)
        old_name : the previous name (only needed for "update")
        """
        if loc is None:
            return
        if action == "add":
            self.loc_by_id[loc.id] = loc
            self.loc_by_name[loc.name.lower()] = loc
        elif action == "remove":
            self.loc_by_id.pop(loc.id, None)
            key = loc.name.lower()
            if self.loc_by_name.get(key) is loc:
                del self.loc_by_name[key]
        elif action == "update":
            self.loc_by_id[loc.id] = loc
            if old_name is not None:
                old_key = old_name.lower()
                if self.loc_by_name.get(old_key) is loc:
                    del self.loc_by_name[old_key]
            self.loc_by_name[loc.name.lower()] = loc

    def invalidate_time_slot(self, action: str, ts: TimeSlot | None) -> None:
        """Update ts_by_id and ts_label_map after a time slot mutation.

        Parameters
        ----------
        action : "add" | "remove"
        ts     : the time slot being mutated
        """
        if ts is None:
            return
        if action == "add":
            self.ts_by_id[ts.id] = ts
            self._index_ts_add(ts)
        elif action == "remove":
            self.ts_by_id.pop(ts.id, None)
            self._index_ts_remove(ts)

    def invalidate_fact(self, action: str, fact: Fact | None) -> None:
        """Update fact_index after a fact add/remove.

        Parameters
        ----------
        action : "add" | "remove"
        fact   : the fact being mutated
        """
        if fact is None:
            return
        triple = (fact.character_id, fact.location_id, fact.time_slot)
        if action == "add":
            self.fact_index.add(triple)
        elif action == "remove":
            self.fact_index.discard(triple)

    def invalidate_deduction(
        self,
        action: str,
        ded: Deduction | None,
        *,
        fact: Fact | None = None,
        rejection: Rejection | None = None,
    ) -> None:
        """Update triple indexes after a deduction state change.

        Parameters
        ----------
        action     : "add" | "accept" | "reject" | "clear_pending"
        ded        : the deduction being mutated (None for "clear_pending")
        fact       : the resulting Fact (only for "accept")
        rejection  : the resulting Rejection (only for "reject")
        """
        if action == "clear_pending":
            self.pending_index.clear()
            return

        if ded is None:
            return

        triple = (ded.character_id, ded.location_id, ded.time_slot)

        if action == "add":
            self.pending_index.add(triple)
        elif action == "accept":
            self.pending_index.discard(triple)
            if fact is not None:
                self.invalidate_fact("add", fact)
        elif action == "reject":
            self.pending_index.discard(triple)
            if rejection is not None:
                self.invalidate_rejection("add", rejection)

    def invalidate_rejection(self, action: str, rej: Rejection | None) -> None:
        """Update rejection_index and rejection_map after a rejection mutation.

        Parameters
        ----------
        action : "add" | "remove"
        rej    : the rejection being mutated
        """
        if rej is None:
            return
        triple = (rej.character_id, rej.location_id, rej.time_slot)
        if action == "add":
            self.rejection_index.add(triple)
            if rej.from_deduction_id is not None:
                self.rejection_map[rej.from_deduction_id] = rej.reason
        elif action == "remove":
            self.rejection_index.discard(triple)
            if rej.from_deduction_id is not None:
                self.rejection_map.pop(rej.from_deduction_id, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_ts_add(self, ts: TimeSlot) -> None:
        """Add a TimeSlot to ts_label_map (first-writer-wins for bare label)."""
        # Full key: "HH:MM(desc)" if has description, else just "HH:MM"
        if ts.description:
            full_key = f"{ts.label}({ts.description})"
            self.ts_label_map[full_key] = ts.id
        # Bare label: first-writer-wins
        if ts.label not in self.ts_label_map:
            self.ts_label_map[ts.label] = ts.id

    def _index_ts_remove(self, ts: TimeSlot) -> None:
        """Remove a TimeSlot from ts_label_map."""
        # Remove full key
        if ts.description:
            full_key = f"{ts.label}({ts.description})"
            self.ts_label_map.pop(full_key, None)
        # Remove bare label only if it points to this ts
        if self.ts_label_map.get(ts.label) == ts.id:
            del self.ts_label_map[ts.label]
