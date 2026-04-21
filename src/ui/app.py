"""Main Flet application — app skeleton with tab navigation and project management.

Provides the main page layout with AppBar, project selector, theme toggle,
and tabbed navigation for the five app sections.
"""

import flet as ft
from loguru import logger

from src.ui.pages.custom import build_custom_tab
from src.ui.pages.manage import build_manage_tab
from src.ui.pages.matrix import build_matrix_tab
from src.ui.pages.review import build_review_tab
from src.ui.pages.scripts import build_scripts_tab
from src.ui.pages.settings import build_settings_tab
from src.ui.state import app_state


def main(page: ft.Page):
    """Flet application entry point."""
    logger.info("app: starting Flet main()")
    page.title = "Puzzle Solver — 剧本杀推理助手"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.window.width = 1400
    page.window.height = 900

    # --- Theme toggle ---
    def toggle_theme(e):
        page.theme_mode = (
            ft.ThemeMode.LIGHT if page.theme_mode == ft.ThemeMode.DARK else ft.ThemeMode.DARK
        )
        page.update()

    # --- Project selector ---
    def on_project_change(e):
        if e.control.value:
            logger.info("app: switching to project id={!r}", e.control.value)
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
            logger.info("app: creating project name={!r}", name)
            app_state.create_project(
                name=name,
                description=desc_field.value.strip() or None,
            )
            dlg.open = False
            if dlg in page.overlay:
                page.overlay.remove(dlg)
            page.update()
            rebuild_content()

        def do_cancel(e):
            dlg.open = False
            if dlg in page.overlay:
                page.overlay.remove(dlg)
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
                ft.Button("创建", on_click=do_create),
            ],
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def _close_dialog(dlg: ft.AlertDialog) -> None:
        dlg.open = False
        if dlg in page.overlay:
            page.overlay.remove(dlg)
        page.update()

    def import_project_from_picker_result(result) -> None:
        selected_files = getattr(result, "files", None) or []
        if not selected_files:
            return

        selected_path = getattr(selected_files[0], "path", None)
        if not selected_path:
            page.snack_bar = ft.SnackBar(ft.Text("未选择有效的 JSON 文件"))
            page.snack_bar.open = True
            page.update()
            return

        try:
            project = app_state.import_project_from_json(selected_path)
        except (ValueError, OSError, NotImplementedError) as exc:
            error_dialog = ft.AlertDialog(
                title=ft.Text("导入失败", color=ft.Colors.RED),
                content=ft.Column(
                    controls=[
                        ft.Text("无法导入所选 JSON 文件。"),
                        ft.Text(f"错误类型：{type(exc).__name__}"),
                        ft.Text(f"详细信息：{exc}", selectable=True),
                        ft.Text(
                            "请确认文件为旧版项目导出的 JSON，且结构完整。",
                            size=12,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    tight=True,
                    spacing=8,
                ),
                actions=[ft.TextButton("关闭", on_click=lambda e: _close_dialog(error_dialog))],
            )
            page.overlay.append(error_dialog)
            error_dialog.open = True
            page.update()
            return

        app_state.current_project = None
        page.snack_bar = ft.SnackBar(ft.Text(f"已导入项目：{project.name}（请在首页选择）"))
        page.snack_bar.open = True
        rebuild_content()

    file_picker = ft.FilePicker()
    file_picker.on_result = import_project_from_picker_result
    page.overlay.append(file_picker)

    async def show_import_project_dialog(e):
        await file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["json"],
            dialog_title="选择旧版 JSON 项目文件",
        )

    # --- Tab content stubs ---
    def scripts_content():
        return build_scripts_tab(page)

    def matrix_content():
        return build_matrix_tab(page)

    def manage_content():
        return build_manage_tab(page)

    def review_content():
        return build_review_tab(page)

    def custom_content():
        return build_custom_tab(page)

    def settings_content():
        return build_settings_tab(page, on_project_deleted=rebuild_content)

    def rebuild_content():
        """Rebuild the entire page content based on current state."""
        page.controls.clear()
        # Preserve file_picker in overlay to keep it functional after rebuild
        preserved_overlays = [c for c in page.overlay if isinstance(c, ft.FilePicker)]
        page.overlay.clear()
        page.overlay.extend(preserved_overlays)

        if app_state.current_project is None:
            page.controls.append(
                _build_landing_page(page, show_create_project_dialog, show_import_project_dialog)
            )
        else:
            page.controls.append(
                _build_project_view(
                    page,
                    on_project_change=on_project_change,
                    show_create_project_dialog=show_create_project_dialog,
                    show_import_project_dialog=show_import_project_dialog,
                    toggle_theme=toggle_theme,
                    scripts_content=scripts_content,
                    matrix_content=matrix_content,
                    manage_content=manage_content,
                    review_content=review_content,
                    custom_content=custom_content,
                    settings_content=settings_content,
                )
            )
        page.update()

    # Initial build
    rebuild_content()


def _build_landing_page(
    page: ft.Page, show_create_project_dialog, show_import_project_dialog
) -> ft.Control:
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
                    ft.Button(
                        "创建新项目",
                        icon=ft.Icons.ADD,
                        on_click=show_create_project_dialog,
                    ),
                    ft.OutlinedButton(
                        "导入旧版 JSON",
                        icon=ft.Icons.UPLOAD_FILE,
                        on_click=show_import_project_dialog,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment.CENTER,
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
            desc_controls.append(ft.Text(proj.description, color=ft.Colors.GREY, size=13))
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
                ft.Button(
                    "创建新项目",
                    icon=ft.Icons.ADD,
                    on_click=show_create_project_dialog,
                ),
                ft.OutlinedButton(
                    "导入旧版 JSON",
                    icon=ft.Icons.UPLOAD_FILE,
                    on_click=show_import_project_dialog,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        padding=40,
    )


def _build_project_view(
    page: ft.Page,
    on_project_change,
    show_create_project_dialog,
    show_import_project_dialog,
    toggle_theme,
    scripts_content,
    matrix_content,
    manage_content,
    review_content,
    custom_content,
    settings_content,
) -> ft.Control:
    """Build the tabbed project view with AppBar, Tabs, and TabBarView."""

    # --- Build project selector dropdown ---
    project_summaries = app_state.list_projects()
    current_id = app_state.current_project.id if app_state.current_project else None
    project_options = [ft.dropdown.Option(key=s.id, text=s.name) for s in project_summaries]
    project_dropdown = ft.Dropdown(
        label="切换项目",
        value=current_id,
        options=project_options,
        on_select=on_project_change,
        width=220,
        dense=True,
        text_size=14,
        color=ft.Colors.WHITE,
        border_color=ft.Colors.WHITE_54,
    )

    # --- Home button ---
    def go_home(e):
        logger.info("app: going home, unloading project")
        app_state.current_project = None
        main(page)

    # --- Tab content mapping ---
    tab_content_builders = [
        scripts_content,
        matrix_content,
        manage_content,
        review_content,
        custom_content,
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
        tab_names = ["剧本", "矩阵", "管理", "审查", "自定义", "设置"]
        logger.debug(
            "app: tab changed → {} ({})", idx, tab_names[idx] if idx < len(tab_names) else "?"
        )
        tab_content_area.content = tab_content_builders[idx]()
        page.update()

    # --- Tabs ---
    tab_bar = ft.TabBar(
        tabs=[
            ft.Tab(label="剧本", icon=ft.Icons.DESCRIPTION),
            ft.Tab(label="矩阵", icon=ft.Icons.GRID_ON),
            ft.Tab(label="管理", icon=ft.Icons.PEOPLE),
            ft.Tab(label="审查", icon=ft.Icons.FACT_CHECK),
            ft.Tab(label="自定义", icon=ft.Icons.PSYCHOLOGY_ALT),
            ft.Tab(label="设置", icon=ft.Icons.SETTINGS),
        ],
    )

    tabs_control = ft.Tabs(
        length=6,
        selected_index=0,
        on_change=on_tab_change,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                tab_bar,
                tab_content_area,
            ],
            spacing=0,
        ),
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
                icon=ft.Icons.UPLOAD_FILE,
                tooltip="导入旧版 JSON",
                on_click=show_import_project_dialog,
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
        ],
        expand=True,
        spacing=0,
    )
