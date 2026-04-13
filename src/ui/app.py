"""Main Flet application — app skeleton with tab navigation and project management.

Provides the main page layout with AppBar, project selector, theme toggle,
and tabbed navigation for the five app sections.
"""

import flet as ft

from src.ui.pages.manage import build_manage_tab
from src.ui.pages.scripts import build_scripts_tab
from src.ui.pages.settings import build_settings_tab
from src.ui.state import app_state


def main(page: ft.Page):
    """Flet application entry point."""
    page.title = "Puzzle Solver — 剧本杀推理助手"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.window.width = 1400
    page.window.height = 900

    # --- Theme toggle ---
    def toggle_theme(e):
        page.theme_mode = (
            ft.ThemeMode.LIGHT
            if page.theme_mode == ft.ThemeMode.DARK
            else ft.ThemeMode.DARK
        )
        page.update()

    # --- Project selector ---
    def on_project_change(e):
        if e.control.value:
            app_state.load_project(e.control.value)
            rebuild_content()

    def show_create_project_dialog(e):
        name_field = ft.TextField(label="项目名称 *", autofocus=True)
        desc_field = ft.TextField(label="描述（可选）")
        error_text = ft.Text("", color=ft.Colors.RED)

        def do_create(e):
            name = name_field.value.strip()
            if not name:
                error_text.value = "项目名称不能为空"
                page.update()
                return
            app_state.create_project(
                name=name,
                description=desc_field.value.strip() or None,
            )
            dlg.open = False
            page.update()
            rebuild_content()

        def do_cancel(e):
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("新建项目"),
            content=ft.Column(
                controls=[
                    name_field,
                    desc_field,
                    error_text,
                    ft.Text(
                        "💡 创建后请前往「剧本」页面添加剧本",
                        size=12,
                        color=ft.Colors.GREY,
                    ),
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("取消", on_click=do_cancel),
                ft.ElevatedButton("创建", on_click=do_create),
            ],
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    # --- Tab content stubs ---
    def scripts_content():
        return build_scripts_tab(page)

    def matrix_content():
        return ft.Text("推理矩阵 — 待实现", size=20)

    def manage_content():
        return build_manage_tab(page)

    def review_content():
        return ft.Text("推断审查 — 待实现", size=20)

    def settings_content():
        return build_settings_tab(page)

    # --- Content area ---
    content_area = ft.Container(expand=True)

    def rebuild_content():
        """Rebuild the entire page content based on current state."""
        page.controls.clear()
        page.overlay.clear()

        if app_state.current_project is None:
            page.controls.append(_build_landing_page(page, show_create_project_dialog))
        else:
            page.controls.append(
                _build_project_view(
                    page,
                    on_project_change=on_project_change,
                    show_create_project_dialog=show_create_project_dialog,
                    toggle_theme=toggle_theme,
                    scripts_content=scripts_content,
                    matrix_content=matrix_content,
                    manage_content=manage_content,
                    review_content=review_content,
                    settings_content=settings_content,
                )
            )
        page.update()

    # Initial build
    rebuild_content()


def _build_landing_page(page: ft.Page, show_create_project_dialog) -> ft.Control:
    """Build the welcome / project selection landing page."""
    projects = app_state.list_projects()

    if not projects:
        # Empty state — prompt to create first project
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("🔍 Puzzle Solver", size=40, weight=ft.FontWeight.BOLD),
                    ft.Text("剧本杀推理助手", size=20, color=ft.Colors.GREY),
                    ft.Container(height=40),
                    ft.Icon(ft.Icons.FOLDER_OPEN, size=64, color=ft.Colors.GREY),
                    ft.Text("暂无项目", size=20),
                    ft.Text(
                        "点击下方按钮创建您的第一个推理项目",
                        color=ft.Colors.GREY,
                    ),
                    ft.Container(height=20),
                    ft.ElevatedButton(
                        "创建新项目",
                        icon=ft.Icons.ADD,
                        on_click=show_create_project_dialog,
                        style=ft.ButtonStyle(padding=20),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.alignment.center,
            expand=True,
            padding=40,
        )

    # Has projects — show project cards
    def make_project_click_handler(project_id):
        def handler(e):
            app_state.load_project(project_id)
            # Rebuild the page from main's rebuild_content
            # We trigger rebuild by calling main again effectively
            main(page)

        return handler

    project_cards = []
    for proj in projects:
        desc_controls = []
        if proj.description:
            desc_controls.append(
                ft.Text(proj.description, color=ft.Colors.GREY, size=13)
            )
        desc_controls.append(
            ft.Row(
                controls=[
                    ft.Text(f"👤 {proj.character_count}", size=12),
                    ft.Text(f"📍 {proj.location_count}", size=12),
                    ft.Text(f"📜 {proj.script_count}", size=12),
                    ft.Text(f"✅ {proj.fact_count}", size=12),
                ],
                spacing=15,
            )
        )
        desc_controls.append(
            ft.Text(
                f"更新于 {proj.updated_at.strftime('%Y-%m-%d %H:%M')}",
                size=11,
                color=ft.Colors.GREY,
            )
        )

        card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(proj.name, size=18, weight=ft.FontWeight.BOLD),
                        *desc_controls,
                    ],
                    spacing=8,
                ),
                padding=20,
                width=280,
                on_click=make_project_click_handler(proj.id),
                ink=True,
            ),
        )
        project_cards.append(card)

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("🔍 Puzzle Solver", size=40, weight=ft.FontWeight.BOLD),
                ft.Text("剧本杀推理助手", size=20, color=ft.Colors.GREY),
                ft.Container(height=30),
                ft.Text("选择一个项目", size=24),
                ft.Container(height=10),
                ft.Row(
                    controls=project_cards,
                    wrap=True,
                    spacing=20,
                    run_spacing=20,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Container(height=20),
                ft.ElevatedButton(
                    "创建新项目",
                    icon=ft.Icons.ADD,
                    on_click=show_create_project_dialog,
                    style=ft.ButtonStyle(padding=20),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        alignment=ft.alignment.center,
        expand=True,
        padding=40,
    )


def _build_project_view(
    page: ft.Page,
    on_project_change,
    show_create_project_dialog,
    toggle_theme,
    scripts_content,
    matrix_content,
    manage_content,
    review_content,
    settings_content,
) -> ft.Control:
    """Build the tabbed project view with AppBar, Tabs, and TabBarView."""

    # --- Build project selector dropdown ---
    project_summaries = app_state.list_projects()
    current_id = (
        app_state.current_project.id if app_state.current_project else None
    )
    project_options = [
        ft.dropdown.Option(key=s.id, text=s.name) for s in project_summaries
    ]
    project_dropdown = ft.Dropdown(
        label="切换项目",
        value=current_id,
        options=project_options,
        on_change=on_project_change,
        width=220,
        dense=True,
        text_size=14,
        color=ft.Colors.WHITE,
        border_color=ft.Colors.WHITE54,
    )

    # --- Home button ---
    def go_home(e):
        app_state.current_project = None
        main(page)

    # --- Tab content mapping ---
    tab_content_builders = [
        scripts_content,
        matrix_content,
        manage_content,
        review_content,
        settings_content,
    ]

    # --- Tab content container ---
    tab_content_area = ft.Container(
        content=tab_content_builders[0](),
        expand=True,
        padding=20,
    )

    def on_tab_change(e):
        idx = e.control.selected_index
        tab_content_area.content = tab_content_builders[idx]()
        page.update()

    # --- Tabs ---
    tabs_control = ft.Tabs(
        content=[
            ft.Tab(label="剧本", icon=ft.Icons.DESCRIPTION),
            ft.Tab(label="矩阵", icon=ft.Icons.GRID_ON),
            ft.Tab(label="管理", icon=ft.Icons.PEOPLE),
            ft.Tab(label="审查", icon=ft.Icons.FACT_CHECK),
            ft.Tab(label="设置", icon=ft.Icons.SETTINGS),
        ],
        length=5,
        selected_index=0,
        on_change=on_tab_change,
    )

    # --- AppBar ---
    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.HOME,
            tooltip="返回首页",
            on_click=go_home,
            icon_color=ft.Colors.WHITE,
        ),
        title=ft.Text(
            f"🔍 {app_state.current_project.name}",
            size=18,
            weight=ft.FontWeight.BOLD,
        ),
        actions=[
            project_dropdown,
            ft.Container(width=10),
            ft.IconButton(
                icon=ft.Icons.ADD,
                tooltip="新建项目",
                on_click=show_create_project_dialog,
                icon_color=ft.Colors.WHITE,
            ),
            ft.IconButton(
                icon=ft.Icons.DARK_MODE,
                tooltip="切换深色/浅色模式",
                on_click=toggle_theme,
                icon_color=ft.Colors.WHITE,
            ),
        ],
        bgcolor=ft.Colors.BLUE_GREY_900,
    )

    return ft.Column(
        controls=[
            appbar,
            tabs_control,
            tab_content_area,
        ],
        expand=True,
        spacing=0,
    )
