"""Pydantic v2 data models for the Puzzle Solver application.

Based on the JSON schema defined in docs/design/data-model.json.
Core concept: a 3D assignment puzzle — Character × Location × Time.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# --- Custom Types ---

TimeSlot = Annotated[str, Field(pattern=r"^\d{2}:\d{2}$", description="Time slot in HH:MM format")]


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
    stated_time: Optional[str] = None
    stated_location: Optional[str] = None
    characters_mentioned: list[str] = Field(default_factory=list)
    source_order: Optional[int] = None
    user_notes: Optional[str] = None


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
    description: Optional[str] = None
    status: CharacterStatus = CharacterStatus.confirmed
    discovered_in_script_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Location(BaseModel):
    """A location in the mystery game."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    discovered_in_script_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Script(BaseModel):
    """A script/scene entry with raw text from the game."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: Optional[str] = None
    raw_text: str
    metadata: ScriptMetadata = Field(default_factory=ScriptMetadata)
    analysis_result: Optional[dict] = None  # Cached AI analysis result
    added_at: datetime = Field(default_factory=datetime.now)


class Fact(BaseModel):
    """A confirmed fact: character X was at location Y at time Z."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    character_id: str
    location_id: str
    time_slot: str
    source_type: SourceType
    source_evidence: Optional[str] = None
    source_script_ids: list[str] = Field(default_factory=list)
    from_deduction_id: Optional[str] = None
    confirmed_at: datetime = Field(default_factory=datetime.now)

    @field_validator("time_slot")
    @classmethod
    def validate_time_slot(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"time_slot must be in HH:MM format, got '{v}'")
        return v


class Rejection(BaseModel):
    """A rejected deduction — serves as a negative constraint."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    character_id: str
    location_id: str
    time_slot: str
    reason: str
    from_deduction_id: Optional[str] = None
    rejected_at: datetime = Field(default_factory=datetime.now)

    @field_validator("time_slot")
    @classmethod
    def validate_time_slot(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"time_slot must be in HH:MM format, got '{v}'")
        return v


class Deduction(BaseModel):
    """An AI-generated deduction candidate pending user review."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    character_id: str
    location_id: str
    time_slot: str
    confidence: ConfidenceLevel
    reasoning: str
    supporting_script_ids: list[str] = Field(default_factory=list)
    depends_on_fact_ids: list[str] = Field(default_factory=list)
    status: DeductionStatus = DeductionStatus.pending
    batch_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None

    @field_validator("time_slot")
    @classmethod
    def validate_time_slot(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"time_slot must be in HH:MM format, got '{v}'")
        return v


class Hint(BaseModel):
    """A game-provided hint or rule that constrains the solution space."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: HintType
    content: str
    applies_to: HintScope = Field(default_factory=HintScope)
    created_at: datetime = Field(default_factory=datetime.now)


# --- Root Model ---

class Project(BaseModel):
    """Top-level game/project container. One project = one mystery game playthrough."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    time_slots: list[str] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    scripts: list[Script] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    rejections: list[Rejection] = Field(default_factory=list)
    deductions: list[Deduction] = Field(default_factory=list)
    hints: list[Hint] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("time_slots")
    @classmethod
    def validate_time_slots(cls, v: list[str]) -> list[str]:
        for ts in v:
            if not re.match(r"^\d{2}:\d{2}$", ts):
                raise ValueError(f"Each time_slot must be in HH:MM format, got '{ts}'")
        return v


class ProjectSummary(BaseModel):
    """Lightweight project summary for listing."""
    id: str
    name: str
    description: Optional[str] = None
    character_count: int = 0
    location_count: int = 0
    script_count: int = 0
    fact_count: int = 0
    created_at: datetime
    updated_at: datetime
