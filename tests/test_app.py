from __future__ import annotations

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
        if isinstance(child, (ft.TextButton, ft.ElevatedButton)) and label == text:
            return child
    raise AssertionError(f"Button with text {text!r} not found")


def test_create_project_dialog_closes_and_is_removed_after_success(monkeypatch):
    stub_state = _StubAppState()
    monkeypatch.setattr(app_module, "app_state", stub_state)

    page = _make_page()
    app_module.main(page)

    landing = page.controls[0]
    create_button = _find_button_by_text(landing, "创建新项目")
    create_button.on_click(None)

    assert len(page.overlay) == 1
    dialog = page.overlay[0]
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
    assert page.overlay == []
    assert len(page.controls) == 1

    project_view = page.controls[0]
    appbar = project_view.controls[0]
    assert isinstance(appbar, ft.AppBar)
    assert appbar.title.value == "🔍 案件一"
