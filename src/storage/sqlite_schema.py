from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class ProjectTable(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(primary_key=True)
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    character_count: int = 0
    location_count: int = 0
    script_count: int = 0
    fact_count: int = 0


class CharacterTable(SQLModel, table=True):
    __tablename__ = "characters"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    name: str
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    description: str | None = None
    status: str
    discovered_in_script_id: str | None = None
    created_at: datetime


class LocationTable(SQLModel, table=True):
    __tablename__ = "locations"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    name: str
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    description: str | None = None
    discovered_in_script_id: str | None = None
    created_at: datetime


class TimeSlotTable(SQLModel, table=True):
    __tablename__ = "time_slots"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    label: str
    description: str = ""
    sort_order: int = 0


class ScriptTable(SQLModel, table=True):
    __tablename__ = "scripts"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    title: str | None = None
    raw_text: str
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    analysis_result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    added_at: datetime


class FactTable(SQLModel, table=True):
    __tablename__ = "facts"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    character_id: str = Field(index=True)
    location_id: str = Field(index=True)
    time_slot: str = Field(index=True)
    source_type: str
    source_evidence: str | None = None
    source_script_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    from_deduction_id: str | None = None
    confirmed_at: datetime


class DeductionTable(SQLModel, table=True):
    __tablename__ = "deductions"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    character_id: str = Field(index=True)
    location_id: str = Field(index=True)
    time_slot: str = Field(index=True)
    confidence: str
    reasoning: str
    supporting_script_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    depends_on_fact_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(index=True)
    batch_id: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class RejectionTable(SQLModel, table=True):
    __tablename__ = "rejections"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    character_id: str = Field(index=True)
    location_id: str = Field(index=True)
    time_slot: str = Field(index=True)
    reason: str
    from_deduction_id: str | None = None
    rejected_at: datetime
