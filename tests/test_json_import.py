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


def test_import_invalid_json_fails_clearly_and_leaves_no_projects(
    sqlite_state: AppState, tmp_path: Path
) -> None:
    source_path = tmp_path / "broken.json"
    source_path.write_text("{ invalid json", encoding="utf-8")

    with pytest.raises(ValueError, match="无法导入 JSON 项目"):
        sqlite_state.import_project_from_json(source_path)

    assert sqlite_state.list_projects() == []
    assert sqlite_state.current_project is None


def test_duplicate_import_replaces_existing_project_without_creating_ambiguous_duplicates(
    sqlite_state: AppState, tmp_path: Path
) -> None:
    source_project = Project(
        id="dup-project",
        name="重复导入项目",
        description="第一次导入",
        characters=[Character(id="char-1", name="阿明")],
    )
    source_path = _write_project_json(tmp_path / "duplicate.json", source_project)

    first_import = sqlite_state.import_project_from_json(source_path)
    sqlite_state.add_character(name="本地修改角色")
    sqlite_state.current_project = None

    updated_source_project = source_project.model_copy(
        update={
            "description": "第二次导入",
            "characters": [Character(id="char-1", name="阿明"), Character(id="char-2", name="阿红")],
        }
    )
    source_path.write_text(updated_source_project.model_dump_json(indent=2), encoding="utf-8")

    second_import = sqlite_state.import_project_from_json(source_path)

    assert first_import.id == second_import.id == "dup-project"
    projects = sqlite_state.list_projects()
    assert [project.id for project in projects] == ["dup-project"]
    assert sqlite_state.current_project is not None
    assert sqlite_state.current_project.id == "dup-project"
    assert sqlite_state.current_project.description == "第二次导入"
    assert [character.id for character in sqlite_state.current_project.characters] == [
        "char-1",
        "char-2",
    ]
    assert all(character.name != "本地修改角色" for character in sqlite_state.current_project.characters)


def test_failed_import_is_atomic_when_store_write_fails(sqlite_state: AppState, tmp_path: Path) -> None:
    existing_project = sqlite_state.create_project(name="原生项目")
    sqlite_state.current_project = None

    source_project = Project(id="atomic-project", name="原子导入项目")
    source_path = _write_project_json(tmp_path / "atomic.json", source_project)

    original_persist = sqlite_state.store._persist_project_records

    def fail_during_persist(session, project: Project) -> None:
        original_persist(session, project)
        raise RuntimeError("boom")

    sqlite_state.store._persist_project_records = fail_during_persist  # type: ignore[method-assign]
    try:
        with pytest.raises(ValueError, match="无法导入 JSON 项目"):
            sqlite_state.import_project_from_json(source_path)
    finally:
        sqlite_state.store._persist_project_records = original_persist  # type: ignore[method-assign]

    projects = sqlite_state.list_projects()
    assert [project.id for project in projects] == [existing_project.id]
    assert sqlite_state.current_project is None


def test_imported_project_edit_reload_cross_flow_parity(sqlite_state: AppState, tmp_path: Path) -> None:
    imported_script = Script(
        id="script-edit",
        title="原始标题",
        raw_text="原始剧本",
        metadata=ScriptMetadata(
            stated_time="09:00",
            stated_location="大厅",
            characters_mentioned=["阿明"],
            source_order=2,
            user_notes="原始备注",
        ),
        analysis_result={
            "characters_mentioned": [{"name": "阿明", "character_id": "char-a", "is_new": False}],
            "locations_mentioned": [{"name": "大厅", "location_id": "loc-hall", "is_new": False}],
            "time_references": [{"time_slot": "09:00", "reference_text": "09:00", "is_explicit": True}],
            "direct_facts": [],
        },
    )
    source_project = Project(
        id="cross-flow-import",
        name="跨流程导入项目",
        description="验证导入后编辑重载",
        time_slots=[
            TimeSlot(id="ts-09", label="09:00", description="早上", sort_order=0),
            TimeSlot(id="ts-10", label="10:00", description="中段", sort_order=1),
        ],
        characters=[Character(id="char-a", name="阿明"), Character(id="char-b", name="阿红")],
        locations=[
            Location(id="loc-hall", name="大厅"),
            Location(id="loc-garden", name="花园"),
            Location(id="loc-study", name="书房"),
        ],
        scripts=[imported_script],
        facts=[
            Fact(
                id="fact-base",
                character_id="char-a",
                location_id="loc-hall",
                time_slot="ts-09",
                source_type=SourceType.script_explicit,
                source_script_ids=["script-edit"],
            )
        ],
        deductions=[
            Deduction(
                id="ded-pending-cross",
                character_id="char-b",
                location_id="loc-garden",
                time_slot="ts-10",
                confidence=ConfidenceLevel.high,
                reasoning="待处理推断",
                supporting_script_ids=["script-edit"],
                status=DeductionStatus.pending,
            )
        ],
    )
    source_path = _write_project_json(tmp_path / "cross-flow.json", source_project)

    imported = sqlite_state.import_project_from_json(source_path)
    original_updated_at = imported.updated_at

    updated_script = sqlite_state.update_script(
        "script-edit",
        title="已编辑标题",
        raw_text="已编辑剧本",
        user_notes="已编辑备注",
    )
    assert updated_script is not None
    assert updated_script.metadata.source_order == 2
    assert updated_script.analysis_result == imported_script.analysis_result

    new_char = sqlite_state.add_character(name="新角色")
    new_loc = sqlite_state.add_location(name="地下室")
    reordered = sqlite_state.reorder_time_slot("ts-10", -1)
    assert reordered is True

    rejection = sqlite_state.reject_deduction("ded-pending-cross")
    assert rejection is not None
    assert rejection.reason == "用户拒绝"
    new_fact = sqlite_state.add_fact(
        character_id=new_char.id,
        location_id=new_loc.id,
        time_slot="ts-09",
        source_type=SourceType.user_input,
        source_evidence="手动补充",
    )
    assert new_fact.source_evidence == "手动补充"

    imported_id = imported.id
    sqlite_state.current_project = None
    sqlite_state.load_project(imported_id)
    reloaded = sqlite_state.current_project
    assert reloaded is not None

    reloaded_script = next(script for script in reloaded.scripts if script.id == "script-edit")
    assert reloaded_script.title == "已编辑标题"
    assert reloaded_script.raw_text == "已编辑剧本"
    assert reloaded_script.metadata.user_notes == "已编辑备注"
    assert reloaded_script.metadata.source_order == 2
    assert reloaded_script.analysis_result == imported_script.analysis_result

    assert reloaded.updated_at > original_updated_at
    assert [ts.id for ts in reloaded.time_slots] == ["ts-10", "ts-09"]
    assert sqlite_state.cache.ts_label_map["10:00"] == "ts-10"
    assert sqlite_state.cache.ts_label_map["09:00"] == "ts-09"
    assert sqlite_state.get_pending_deductions() == []
    assert any(r.from_deduction_id == "ded-pending-cross" for r in reloaded.rejections)
    assert ("char-b", "loc-garden", "ts-10") in sqlite_state._rejection_index
    assert ("char-b", "loc-garden", "ts-10") not in sqlite_state._pending_index
    assert ("char-a", "loc-hall", "ts-09") in sqlite_state._fact_index
    assert (new_char.id, new_loc.id, "ts-09") in sqlite_state._fact_index
    assert any(character.id == new_char.id for character in reloaded.characters)
    assert any(location.id == new_loc.id for location in reloaded.locations)
    assert any(fact.id == "fact-base" for fact in reloaded.facts)
    assert any(fact.id == new_fact.id for fact in reloaded.facts)
