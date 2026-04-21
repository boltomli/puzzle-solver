from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

import flet as ft

from src.models.puzzle import ProjectSummary
from src.ui import app as app_module


class _StubConnection:
    loop = None
    executor = None
    page_url = ""
    page_name = ""


class _StubSession:
    __slots__ = ("index", "connection", "pubsub_client", "__weakref__")

    def __init__(self) -> None:
        self.index = {}
        self.connection = _StubConnection()
        self.pubsub_client = None

    def patch_control(self, control) -> None:
        return None

    def start_updates_scheduler(self) -> None:
        return None

    def schedule_update(self, control) -> None:
        return None

    def error(self, message: str) -> None:
        return None


@dataclass
class _CreateCall:
    name: str
    description: str | None


class _StubAppState:
    def __init__(self) -> None:
        self.current_project = None
        self.project_summaries: list[ProjectSummary] = []
        self.create_calls: list[_CreateCall] = []
        self.import_calls: list[str] = []
        self.imported_project = None

    def list_projects(self) -> list[ProjectSummary]:
        return list(self.project_summaries)

    def create_project(self, name: str, description: str | None = None, time_slots=None):
        self.create_calls.append(_CreateCall(name=name, description=description))
        self.current_project = type(
            "Project",
            (),
            {"id": "new-project", "name": name, "updated_at": datetime(2026, 4, 21, 12, 0)},
        )()
        self.project_summaries = [
            ProjectSummary(
                id="new-project",
                name=name,
                description=description,
                character_count=0,
                location_count=0,
                script_count=0,
                fact_count=0,
                created_at=self.current_project.updated_at,
                updated_at=self.current_project.updated_at,
            )
        ]
        return self.current_project

    def load_project(self, project_id: str) -> None:
        return None

    def import_project_from_json(self, json_path: str):
        self.import_calls.append(json_path)
        self.current_project = self.imported_project
        return self.imported_project


def _make_page() -> ft.Page:
    session = _StubSession()
    page = ft.Page(session, test=True)
    page._test_session = session
    return page


def _walk_controls(control):
    yield control
    for child_name in ("controls", "actions", "tabs"):
        children = getattr(control, child_name, None)
        if children:
            for child in children:
                yield from _walk_controls(child)
    for child_name in ("content", "title", "leading"):
        child = getattr(control, child_name, None)
        if child is not None:
            yield from _walk_controls(child)


def _find_text_field_by_label(control, label: str) -> ft.TextField:
    for child in _walk_controls(control):
        if isinstance(child, ft.TextField) and child.label == label:
            return child
    raise AssertionError(f"TextField with label {label!r} not found")


def _find_button_by_text(control, text: str):
    for child in _walk_controls(control):
        label = getattr(child, "text", None)
        if label is None:
            label = getattr(child, "content", None)
        if isinstance(child, (ft.TextButton, ft.ElevatedButton, ft.OutlinedButton, ft.Button)) and label == text:
            return child
    raise AssertionError(f"Button with text {text!r} not found")


def _find_control_by_tooltip(control, tooltip: str):
    for child in _walk_controls(control):
        if getattr(child, "tooltip", None) == tooltip:
            return child
    raise AssertionError(f"Control with tooltip {tooltip!r} not found")


def test_create_project_dialog_closes_and_is_removed_after_success(monkeypatch):
    stub_state = _StubAppState()
    monkeypatch.setattr(app_module, "app_state", stub_state)

    page = _make_page()
    app_module.main(page)

    landing = page.controls[0]
    create_button = _find_button_by_text(landing, "创建新项目")
    create_button.on_click(None)

    # Filter out FilePicker from overlay to find the dialog
    dialogs = [c for c in page.overlay if isinstance(c, ft.AlertDialog)]
    assert len(dialogs) == 1
    dialog = dialogs[0]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.open is True

    name_field = _find_text_field_by_label(dialog, "项目名称 *")
    desc_field = _find_text_field_by_label(dialog, "描述（可选）")
    name_field.value = "案件一"
    desc_field.value = "初始描述"

    submit_button = _find_button_by_text(dialog, "创建")
    submit_button.on_click(None)

    assert stub_state.create_calls == [_CreateCall(name="案件一", description="初始描述")]
    assert stub_state.current_project is not None
    assert stub_state.current_project.name == "案件一"
    assert len(page.controls) == 1

    project_view = page.controls[0]
    appbar = project_view.controls[0]
    assert isinstance(appbar, ft.AppBar)
    assert appbar.title.value == "🔍 案件一"


def test_landing_page_import_entrypoint_picks_json_and_returns_to_landing(monkeypatch):
    stub_state = _StubAppState()
    imported_at = datetime(2026, 4, 21, 13, 0)
    stub_state.imported_project = type(
        "Project",
        (),
        {"id": "imported-project", "name": "旧项目", "updated_at": imported_at},
    )()
    stub_state.project_summaries = [
        ProjectSummary(
            id="imported-project",
            name="旧项目",
            description="来自旧版 JSON",
            character_count=1,
            location_count=1,
            script_count=1,
            fact_count=1,
            created_at=imported_at,
            updated_at=imported_at,
        )
    ]
    monkeypatch.setattr(app_module, "app_state", stub_state)

    captured_picker: dict[str, ft.FilePicker] = {}

    class _StubFilePicker:
        def __init__(self, on_result=None):
            self.on_result = on_result
            self.pick_calls: list[dict] = []
            self.awaited_pick_calls: list[dict] = []
            captured_picker["picker"] = self

        async def pick_files(self, **kwargs):
            self.pick_calls.append(kwargs)
            await asyncio.sleep(0)
            self.awaited_pick_calls.append(kwargs)
            # Return files directly (new API in Flet 0.80+)
            return [
                type("PickedFile", (), {"path": r"C:\legacy\case.json"})(),
            ]

    monkeypatch.setattr(app_module.ft, "FilePicker", _StubFilePicker)

    page = _make_page()
    app_module.main(page)

    landing = page.controls[0]
    import_button = _find_button_by_text(landing, "导入旧版 JSON")
    asyncio.run(import_button.on_click(None))

    picker = captured_picker["picker"]
    assert picker.pick_calls == [
        {
            "allow_multiple": False,
            "allowed_extensions": ["json"],
            "dialog_title": "选择旧版 JSON 项目文件",
        }
    ]
    assert picker.awaited_pick_calls == picker.pick_calls
    assert "picker" in captured_picker

    assert stub_state.import_calls == [r"C:\legacy\case.json"]
    assert stub_state.current_project is None
    assert len(page.controls) == 1
    landing_after_import = page.controls[0]
    _find_button_by_text(landing_after_import, "创建新项目")
    assert page.snack_bar is not None
    assert page.snack_bar.content.value == "已导入项目：旧项目（请在首页选择）"


def test_project_view_import_entrypoint_shows_error_dialog_when_import_fails(monkeypatch):
    stub_state = _StubAppState()
    current_at = datetime(2026, 4, 21, 14, 0)
    stub_state.current_project = type(
        "Project",
        (),
        {"id": "current-project", "name": "当前项目", "updated_at": current_at},
    )()
    stub_state.project_summaries = [
        ProjectSummary(
            id="current-project",
            name="当前项目",
            description=None,
            character_count=0,
            location_count=0,
            script_count=0,
            fact_count=0,
            created_at=current_at,
            updated_at=current_at,
        )
    ]

    def _raise_import(json_path: str):
        raise ValueError(f"无法导入 JSON 项目：{json_path}")

    stub_state.import_project_from_json = _raise_import
    monkeypatch.setattr(app_module, "app_state", stub_state)

    captured_picker: dict[str, ft.FilePicker] = {}

    class _StubFilePicker:
        def __init__(self, on_result=None):
            self.on_result = on_result
            self.pick_calls: list[dict] = []
            self.awaited_pick_calls: list[dict] = []
            captured_picker["picker"] = self

        async def pick_files(self, **kwargs):
            self.pick_calls.append(kwargs)
            await asyncio.sleep(0)
            self.awaited_pick_calls.append(kwargs)
            # Return files directly (new API in Flet 0.80+)
            return [
                type("PickedFile", (), {"path": r"C:\legacy\broken.json"})(),
            ]

    monkeypatch.setattr(app_module.ft, "FilePicker", _StubFilePicker)

    page = _make_page()
    app_module.main(page)

    project_view = page.controls[0]
    appbar = project_view.controls[0]
    import_button = _find_control_by_tooltip(appbar, "导入旧版 JSON")
    asyncio.run(import_button.on_click(None))

    picker = captured_picker["picker"]
    assert picker.awaited_pick_calls == [
        {
            "allow_multiple": False,
            "allowed_extensions": ["json"],
            "dialog_title": "选择旧版 JSON 项目文件",
        }
    ]

    assert stub_state.current_project.name == "当前项目"
    assert len(page.controls) == 1
    current_view = page.controls[0]
    current_appbar = current_view.controls[0]
    assert isinstance(current_appbar, ft.AppBar)
    assert current_appbar.title.value == "🔍 当前项目"
    assert page.overlay
    error_dialog = page.overlay[-1]
    assert isinstance(error_dialog, ft.AlertDialog)
    assert error_dialog.open is True
    assert error_dialog.title.value == "导入失败"
