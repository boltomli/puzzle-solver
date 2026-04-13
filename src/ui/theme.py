"""Shared UI theme and layout for the Puzzle Solver app.

Provides the main page layout with header, project selector, and tab navigation.
"""

import os
import sys

from nicegui import ui

from src.ui.state import app_state
from src.ui.pages.scripts import scripts_tab_content
from src.ui.pages.matrix import matrix_tab_content
from src.ui.pages.manage import manage_tab_content
from src.ui.pages.review import review_tab_content
from src.ui.pages.settings import settings_tab_content


def _show_create_project_dialog():
    """Show a dialog for creating a new project.

    Simplified: only name and optional description.
    Time slots will be extracted automatically by AI from scripts.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("新建项目").classes("text-h6 q-mb-md")

        name_input = ui.input(
            label="项目名称 *",
            placeholder="例如：长津湖剧本杀",
        ).classes("w-full")

        desc_input = ui.input(
            label="描述（可选）",
            placeholder="简短描述此项目",
        ).classes("w-full")

        ui.label("💡 创建后请前往「剧本」页面添加剧本，AI 将自动提取人物、地点和时间段").classes(
            "text-caption text-grey q-mt-sm"
        )

        error_label = ui.label("").classes("text-negative")

        def do_create():
            name = name_input.value.strip()
            if not name:
                error_label.text = "项目名称不能为空"
                return

            app_state.create_project(
                name=name,
                description=desc_input.value.strip() or None,
            )
            ui.notify(f"项目 '{name}' 已创建", type="positive")
            dialog.close()

        with ui.row().classes("w-full justify-end q-mt-md"):
            ui.button("取消", on_click=dialog.close).props("flat")
            ui.button("创建", on_click=do_create, icon="add").props("color=primary")

    dialog.open()


def create_app():
    """Create and configure the NiceGUI application with tabs layout."""

    @ui.page("/")
    def main_page():
        # CRITICAL: Clear previous callbacks to prevent accumulation
        # (each page load registers a new callback)
        app_state.clear_callbacks()

        # Dark mode support — use a toggle-able dark mode
        dark = ui.dark_mode(True)

        # --- Main content rendering (no @ui.refreshable needed) ---
        def main_content():
            if app_state.current_project is None:
                _render_landing_page()
            else:
                _render_project_view(dark)

        # Register state change callback — navigate for a clean re-render
        def on_state_change():
            ui.navigate.to('/')

        app_state.on_change(on_state_change)

        # --- Header ---
        with ui.header().classes("items-center justify-between"):
            ui.label("🔍 Puzzle Solver").classes(
                "text-h6 text-weight-bold cursor-pointer"
            ).on("click", lambda: _go_home())

            with ui.row().classes("items-center gap-2"):
                if app_state.current_project:
                    ui.label(
                        f"📁 {app_state.current_project.name}"
                    ).classes("text-subtitle1")

                # Project selector dropdown
                project_summaries = app_state.list_projects()
                if project_summaries:
                    options = {s.id: s.name for s in project_summaries}
                    current_id = (
                        app_state.current_project.id
                        if app_state.current_project
                        else None
                    )
                    project_select = ui.select(
                        options=options,
                        value=current_id,
                        label="切换项目",
                        on_change=lambda e: _switch_project(e.value),
                    ).classes("min-w-[200px]").props("dense outlined dark")

                ui.button(
                    "新建项目",
                    on_click=_show_create_project_dialog,
                    icon="add",
                ).props("flat dense dark")

                # Dark mode toggle button
                def toggle_dark():
                    dark.toggle()

                ui.button(
                    icon="dark_mode",
                    on_click=toggle_dark,
                ).props("flat dense dark round").tooltip("切换深色/浅色模式")

        # Render main content
        main_content()

    def _go_home():
        """Go back to landing page (unload project)."""
        app_state.current_project = None
        ui.navigate.to('/')

    def _switch_project(project_id: str):
        """Switch to a different project."""
        if project_id:
            app_state.load_project(project_id)

    def _render_landing_page():
        """Render the welcome / project selection screen."""
        with ui.column().classes("w-full items-center q-pa-xl"):
            ui.label("🔍 Puzzle Solver").classes("text-h3 q-mb-sm")
            ui.label("剧本杀推理助手").classes("text-h6 text-grey q-mb-lg")

            projects = app_state.list_projects()
            if not projects:
                with ui.card().classes("w-full max-w-lg q-pa-lg text-center"):
                    ui.icon("folder_open", size="4em", color="grey")
                    ui.label("暂无项目").classes("text-h6 q-mt-md")
                    ui.label("点击下方按钮创建您的第一个推理项目").classes(
                        "text-body1 text-grey"
                    )
                    ui.button(
                        "创建新项目",
                        on_click=_show_create_project_dialog,
                        icon="add",
                    ).classes("q-mt-md").props("color=primary size=lg")
            else:
                ui.label("选择一个项目").classes("text-h5 q-mb-md")
                with ui.row().classes("w-full max-w-4xl flex-wrap justify-center gap-4"):
                    for proj in projects:
                        with ui.card().classes(
                            "cursor-pointer w-72 hover:shadow-lg"
                        ).on(
                            "click",
                            lambda p_id=proj.id: app_state.load_project(p_id),
                        ):
                            with ui.card_section():
                                ui.label(proj.name).classes("text-h6")
                                if proj.description:
                                    ui.label(proj.description).classes(
                                        "text-body2 text-grey"
                                    )
                            with ui.card_section():
                                with ui.row().classes("gap-4 text-caption"):
                                    ui.label(f"👤 {proj.character_count} 人物")
                                    ui.label(f"📍 {proj.location_count} 地点")
                                    ui.label(f"📜 {proj.script_count} 剧本")
                                    ui.label(f"✅ {proj.fact_count} 事实")
                            with ui.card_section():
                                ui.label(
                                    f"更新于 {proj.updated_at.strftime('%Y-%m-%d %H:%M')}"
                                ).classes("text-caption text-grey")

                with ui.row().classes("q-mt-lg"):
                    ui.button(
                        "创建新项目",
                        on_click=_show_create_project_dialog,
                        icon="add",
                    ).props("color=primary size=lg")

    def _render_project_view(dark=None):
        """Render the tabbed project view."""
        # Tab navigation
        pending_count = len(app_state.get_pending_deductions())

        with ui.tabs().classes("w-full") as tabs:
            ui.tab("scripts", label="剧本", icon="description")
            ui.tab("matrix", label="矩阵", icon="grid_on")
            ui.tab("manage", label="管理", icon="people")
            with ui.tab("review", label="审查", icon="fact_check"):
                if pending_count > 0:
                    ui.badge(str(pending_count), color="red").props("floating")
            ui.tab("settings", label="设置", icon="settings")

        # Tab panels
        with ui.tab_panels(tabs, value="scripts").classes("w-full flex-grow"):
            with ui.tab_panel("scripts"):
                scripts_tab_content()
            with ui.tab_panel("matrix"):
                matrix_tab_content()
            with ui.tab_panel("manage"):
                manage_tab_content()
            with ui.tab_panel("review"):
                review_tab_content()
            with ui.tab_panel("settings"):
                settings_tab_content()

    # Determine run mode
    native_mode = os.environ.get("PUZZLE_SOLVER_WEB", "").lower() not in (
        "1",
        "true",
        "yes",
    )

    # Check command-line args for web mode override
    if "--web" in sys.argv:
        native_mode = False

    if native_mode:
        ui.run(
            native=True,
            title="Puzzle Solver",
            window_size=(1400, 900),
            reload=False,
        )
    else:
        ui.run(
            native=False,
            title="Puzzle Solver",
            port=8080,
            reload=False,
        )
