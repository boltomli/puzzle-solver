from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.models.puzzle import (
    Character,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    Fact,
    Location,
    Project,
    Rejection,
    Script,
    ScriptMetadata,
    SourceType,
    TimeSlot,
)
from src.storage.sqlite_repository import SQLiteRepository
from src.storage.sqlite_store import SQLiteStore
from src.ui.state import AppState


@pytest.fixture
def sqlite_state(tmp_path: Path) -> AppState:
    return AppState(store=SQLiteStore(db_path=tmp_path / "projects.db"))


def _write_project_json(path: Path, project: Project) -> Path:
    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_startup_does_not_scan_legacy_json_projects(tmp_path: Path) -> None:
    legacy_project = Project(name="旧项目")
    _write_project_json(tmp_path / f"{legacy_project.id}.json", legacy_project)

    repo = SQLiteRepository(store=SQLiteStore(db_path=tmp_path / "projects.db"))

    assert repo.list_projects() == []


def test_import_json_project_creates_usable_sqlite_project(sqlite_state: AppState, tmp_path: Path) -> None:
    imported_script = Script(
        id="script-1",
        title="第一幕",
        raw_text="线索内容",
        metadata=ScriptMetadata(
            stated_time="20:00",
            stated_location="大厅",
            characters_mentioned=["阿明"],
            source_order=3,
            user_notes="重点关注",
        ),
        analysis_result={
            "characters_mentioned": [{"name": "阿明", "character_id": "char-1", "is_new": False}],
            "direct_facts": [{"character_name": "阿明", "location_name": "大厅", "time_slot": "20:00"}],
        },
    )
    source_project = Project(
        id="project-json-1",
        name="导入项目",
        description="来自旧 JSON",
        time_slots=[TimeSlot(id="ts-1", label="20:00", description="第一晚", sort_order=0)],
        characters=[Character(id="char-1", name="阿明", aliases=["明"], description="证人")],
        locations=[Location(id="loc-1", name="大厅", aliases=["主厅"], description="案发现场")],
        scripts=[imported_script],
        facts=[
            Fact(
                id="fact-1",
                character_id="char-1",
                location_id="loc-1",
                time_slot="ts-1",
                source_type=SourceType.script_explicit,
                source_evidence="剧本明确提到",
                source_script_ids=["script-1"],
            )
        ],
        deductions=[
            Deduction(
                id="ded-pending",
                character_id="char-1",
                location_id="loc-1",
                time_slot="ts-1",
                confidence=ConfidenceLevel.high,
                reasoning="待确认推断",
                supporting_script_ids=["script-1"],
                status=DeductionStatus.pending,
            ),
            Deduction(
                id="ded-accepted",
                character_id="char-1",
                location_id="loc-1",
                time_slot="ts-1",
                confidence=ConfidenceLevel.certain,
                reasoning="已接受推断",
                supporting_script_ids=["script-1"],
                status=DeductionStatus.accepted,
            ),
            Deduction(
                id="ded-rejected",
                character_id="char-1",
                location_id="loc-1",
                time_slot="ts-1",
                confidence=ConfidenceLevel.low,
                reasoning="已拒绝推断",
                supporting_script_ids=["script-1"],
                status=DeductionStatus.rejected,
            ),
        ],
        rejections=[
            Rejection(
                id="rej-1",
                character_id="char-1",
                location_id="loc-1",
                time_slot="ts-1",
                reason="证据不足",
                from_deduction_id="ded-rejected",
            )
        ],
    )
    source_path = _write_project_json(tmp_path / "importable.json", source_project)

    imported = sqlite_state.import_project_from_json(source_path)

    assert imported.id == source_project.id
    assert sqlite_state.current_project is not None
    assert sqlite_state.current_project.id == source_project.id
    assert sqlite_state.current_project.name == "导入项目"
    assert sqlite_state.current_project.description == "来自旧 JSON"
    assert sqlite_state.current_project.characters[0].id == "char-1"
    assert sqlite_state.current_project.locations[0].id == "loc-1"
    assert sqlite_state.current_project.scripts[0].id == "script-1"
    assert sqlite_state.current_project.scripts[0].analysis_result == imported_script.analysis_result
    assert sqlite_state.current_project.facts[0].id == "fact-1"
    assert sqlite_state.current_project.facts[0].source_script_ids == ["script-1"]
    assert {d.id for d in sqlite_state.current_project.deductions} == {
        "ded-pending",
        "ded-accepted",
        "ded-rejected",
    }
    assert sqlite_state.current_project.rejections[0].from_deduction_id == "ded-rejected"
    assert sqlite_state.list_projects()[0].id == source_project.id


def test_import_legacy_string_time_slots_rewrites_references(sqlite_state: AppState, tmp_path: Path) -> None:
    legacy_payload = {
        "id": "legacy-project",
        "name": "旧格式项目",
        "description": "字符串时间段",
        "time_slots": ["08:00", "12:00"],
        "characters": [{"id": "char-1", "name": "Alice", "aliases": [], "status": "confirmed"}],
        "locations": [{"id": "loc-1", "name": "Library", "aliases": []}],
        "scripts": [
            {
                "id": "script-1",
                "title": "Legacy",
                "raw_text": "旧剧本",
                "metadata": {"source_order": 1},
                "analysis_result": {"raw": True},
            }
        ],
        "facts": [
            {
                "id": "fact-1",
                "character_id": "char-1",
                "location_id": "loc-1",
                "time_slot": "08:00",
                "source_type": "user_input",
                "source_script_ids": ["script-1"],
            }
        ],
        "deductions": [
            {
                "id": "ded-1",
                "character_id": "char-1",
                "location_id": "loc-1",
                "time_slot": "12:00",
                "confidence": "medium",
                "reasoning": "legacy ded",
                "supporting_script_ids": ["script-1"],
                "status": "pending",
            }
        ],
        "rejections": [
            {
                "id": "rej-1",
                "character_id": "char-1",
                "location_id": "loc-1",
                "time_slot": "12:00",
                "reason": "legacy rej",
                "from_deduction_id": "ded-1",
            }
        ],
    }
    source_path = tmp_path / "legacy.json"
    source_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    imported = sqlite_state.import_project_from_json(source_path)

    ts_by_label = {ts.label: ts.id for ts in imported.time_slots}
    assert imported.facts[0].time_slot == ts_by_label["08:00"]
    assert imported.deductions[0].time_slot == ts_by_label["12:00"]
    assert imported.rejections[0].time_slot == ts_by_label["12:00"]
    assert imported.scripts[0].analysis_result == {"raw": True}


def test_import_does_not_mutate_source_json(sqlite_state: AppState, tmp_path: Path) -> None:
    source_project = Project(name="源文件保护")
    source_path = _write_project_json(tmp_path / "source.json", source_project)
    before = hashlib.sha256(source_path.read_bytes()).hexdigest()

    sqlite_state.import_project_from_json(source_path)

    after = hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert after == before
