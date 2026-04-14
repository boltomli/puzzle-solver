"""Pydantic v2 data models for the Puzzle Solver application.

Based on the JSON schema defined in docs/design/data-model.json.
Core concept: a 3D assignment puzzle — Character × Location × Time.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# --- Enums ---


class CharacterStatus(str, Enum):
    """Status of a character's identity certainty."""

    confirmed = "confirmed"
    suspected = "suspected"
    unknown = "unknown"


class SourceType(str, Enum):
    """How a fact was established."""

    script_explicit = "script_explicit"
    user_input = "user_input"
    ai_deduction = "ai_deduction"
    game_hint = "game_hint"


class ConfidenceLevel(str, Enum):
    """AI confidence level for a deduction."""

    certain = "certain"
    high = "high"
    medium = "medium"
    low = "low"


class DeductionStatus(str, Enum):
    """Review status of a deduction."""

    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class HintType(str, Enum):
    """Type of hint/rule/constraint."""

    rule = "rule"
    hint = "hint"
    constraint = "constraint"


# --- Sub-models ---


class ScriptMetadata(BaseModel):
    """Metadata extracted from or annotated on a script."""

    stated_time: str | None = None
    stated_location: str | None = None
    characters_mentioned: list[str] = Field(default_factory=list)
    source_order: int | None = None
    user_notes: str | None = None


class HintScope(BaseModel):
    """Scope limiter for a hint — which entities it applies to."""

    character_ids: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    time_slots: list[str] = Field(default_factory=list)


# --- Core Entity Models ---


class Character(BaseModel):
    """A character in the mystery game."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    status: CharacterStatus = CharacterStatus.confirmed
    discovered_in_script_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class Location(BaseModel):
    """A location in the mystery game."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    discovered_in_script_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class TimeSlot(BaseModel):
    """A time slot in the mystery game with unique ID."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    label: str  # HH:MM format, e.g., "16:00"
    description: str = ""  # Optional context, e.g., "第一天", "Day 2"
    sort_order: int = 0  # For manual reordering

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"Time slot label must be HH:MM format, got {v!r}")
        return v


class Script(BaseModel):
    """A script/scene entry with raw text from the game."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str | None = None
    raw_text: str
    metadata: ScriptMetadata = Field(default_factory=ScriptMetadata)
    analysis_result: dict | None = None  # Cached AI analysis result
    added_at: datetime = Field(default_factory=datetime.now)


class Fact(BaseModel):
    """A confirmed fact: character X was at location Y at time Z."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    character_id: str
    location_id: str
    time_slot: str  # TimeSlot ID reference
    source_type: SourceType
    source_evidence: str | None = None
    source_script_ids: list[str] = Field(default_factory=list)
    from_deduction_id: str | None = None
    confirmed_at: datetime = Field(default_factory=datetime.now)


class Rejection(BaseModel):
    """A rejected deduction — serves as a negative constraint."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    character_id: str
    location_id: str
    time_slot: str  # TimeSlot ID reference
    reason: str
    from_deduction_id: str | None = None
    rejected_at: datetime = Field(default_factory=datetime.now)


class Deduction(BaseModel):
    """An AI-generated deduction candidate pending user review."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    character_id: str
    location_id: str
    time_slot: str  # TimeSlot ID reference
    confidence: ConfidenceLevel
    reasoning: str
    supporting_script_ids: list[str] = Field(default_factory=list)
    depends_on_fact_ids: list[str] = Field(default_factory=list)
    status: DeductionStatus = DeductionStatus.pending
    batch_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None


class Hint(BaseModel):
    """A game-provided hint or rule that constrains the solution space."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: HintType
    content: str
    applies_to: HintScope = Field(default_factory=HintScope)
    created_at: datetime = Field(default_factory=datetime.now)


class EntityKind(str, Enum):
    """Which kind of entity an IgnoredEntity refers to."""

    character = "character"
    location = "location"
    time_slot = "time_slot"


class IgnoredEntity(BaseModel):
    """A raw entity name that the user has chosen to permanently ignore.

    When AI analysis surfaces a name that matches an entry here it will not
    be presented to the user again as a 'new entity' suggestion.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: EntityKind
    name: str  # raw name as returned by AI, case-insensitive match
    created_at: datetime = Field(default_factory=datetime.now)


# --- Root Model ---


class Project(BaseModel):
    """Top-level game/project container. One project = one mystery game playthrough."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str | None = None
    time_slots: list[TimeSlot] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    scripts: list[Script] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    rejections: list[Rejection] = Field(default_factory=list)
    deductions: list[Deduction] = Field(default_factory=list)
    hints: list[Hint] = Field(default_factory=list)
    ignored_entities: list[IgnoredEntity] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    @classmethod
    def _migrate_time_slots(cls, data: Any) -> Any:
        """Migrate old string time_slots to TimeSlot objects."""
        if isinstance(data, dict) and "time_slots" in data:
            ts_list = data["time_slots"]
            if ts_list and isinstance(ts_list[0], str):
                label_to_id: dict[str, str] = {}
                new_ts = []
                for i, label in enumerate(ts_list):
                    ts_id = uuid4().hex[:8]
                    new_ts.append({"id": ts_id, "label": label, "sort_order": i})
                    label_to_id[label] = ts_id
                data["time_slots"] = new_ts
                # Migrate references in facts, deductions, rejections
                for item in data.get("facts", []):
                    if isinstance(item, dict):
                        old_val = item.get("time_slot", "")
                        if old_val in label_to_id:
                            item["time_slot"] = label_to_id[old_val]
                    elif hasattr(item, "time_slot") and item.time_slot in label_to_id:
                        item.time_slot = label_to_id[item.time_slot]
                for item in data.get("deductions", []):
                    if isinstance(item, dict):
                        old_val = item.get("time_slot", "")
                        if old_val in label_to_id:
                            item["time_slot"] = label_to_id[old_val]
                    elif hasattr(item, "time_slot") and item.time_slot in label_to_id:
                        item.time_slot = label_to_id[item.time_slot]
                for item in data.get("rejections", []):
                    if isinstance(item, dict):
                        old_val = item.get("time_slot", "")
                        if old_val in label_to_id:
                            item["time_slot"] = label_to_id[old_val]
                    elif hasattr(item, "time_slot") and item.time_slot in label_to_id:
                        item.time_slot = label_to_id[item.time_slot]
        return data


class ProjectSummary(BaseModel):
    """Lightweight project summary for listing."""

    id: str
    name: str
    description: str | None = None
    character_count: int = 0
    location_count: int = 0
    script_count: int = 0
    fact_count: int = 0
    created_at: datetime
    updated_at: datetime
