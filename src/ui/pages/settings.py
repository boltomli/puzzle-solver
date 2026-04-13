"""设置页面 — Settings tab (Flet version).

API configuration: base URL, key, model, system prompt override.
Model list loading with selection dialog.
Project management: delete project (danger zone).
"""

import flet as ft

from src.services.config import load_config, save_config
from src.ui.state import app_state


def build_settings_tab(page: ft.Page) -> ft.Control:
    """Build and return the settings tab control tree.

    Provides:
    - API configuration form (base URL, API key, model, system prompt)
    - Save, test connection, and load models buttons
    - Danger zone: delete current project with two-step confirmation
    """
    config = load_config()

    # --- API configuration fields ---
    base_url_field = ft.TextField(
        label="API Base URL",
        value=config.get("api_base_url", ""),
        hint_text="https://api.openai.com/v1",
    )

    api_key_field = ft.TextField(
        label="API Key（部分服务商可留空）",
        value=config.get("api_key", ""),
        hint_text="sk-...（Ollama 等本地服务可留空）",
        password=True,
        can_reveal_password=True,
    )

    model_field = ft.TextField(
        label="模型名称",
        value=config.get("model", ""),
        hint_text="gpt-4o / deepseek-chat / llama3",
    )

    system_prompt_field = ft.TextField(
        label="自定义系统提示词（可选）",
        value=config.get("system_prompt_override", ""),
        hint_text="覆盖默认的系统提示词。留空则使用内置提示词。",
        multiline=True,
        min_lines=3,
    )

    # --- Helper: collect config from fields ---
    def _collect_config() -> dict:
        return {
            "api_base_url": base_url_field.value.strip(),
            "api_key": api_key_field.value.strip(),
            "model": model_field.value.strip(),
            "system_prompt_override": system_prompt_field.value.strip(),
        }

    # --- Helper: show snack bar ---
    def _show_snackbar(message: str, color: str | None = None):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=color,
        )
        page.snack_bar.open = True
        page.update()

    # --- Save config handler ---
    def on_save_config(e):
        save_config(_collect_config())
        _show_snackbar("配置已保存", ft.Colors.GREEN)

    # --- Test connection handler ---
    async def on_test_connection(e):
        base_url = base_url_field.value.strip()
        model = model_field.value.strip()
        if not base_url or not model:
            _show_snackbar("请先填写 API Base URL 和模型名称", ft.Colors.AMBER)
            return

        # Save config first so LLMService can read it
        save_config(_collect_config())
        _show_snackbar("正在测试连接...")

        try:
            from src.services.llm_service import LLMService

            llm = LLMService()
            reply = await llm.test_connection()
            _show_snackbar(f"连接成功！模型响应: {reply}", ft.Colors.GREEN)
        except Exception as exc:
            _show_snackbar(f"连接失败: {str(exc)[:200]}", ft.Colors.RED)

    # --- Load models handler ---
    async def on_load_models(e):
        base_url = base_url_field.value.strip()
        if not base_url:
            _show_snackbar("请先填写 API Base URL", ft.Colors.AMBER)
            return

        # Save config first so LLMService can read it
        save_config(_collect_config())
        _show_snackbar("正在加载模型列表...")

        try:
            from src.services.llm_service import LLMService

            llm = LLMService()
            models = await llm.list_models()

            if not models:
                _show_snackbar("未发现可用模型", ft.Colors.AMBER)
                return

            # Build model selection dialog
            def make_model_select_handler(model_name: str):
                def handler(e):
                    model_field.value = model_name
                    dlg.open = False
                    page.update()

                return handler

            model_tiles = [
                ft.ListTile(
                    title=ft.Text(m),
                    on_click=make_model_select_handler(m),
                )
                for m in models
            ]

            def close_dialog(e):
                dlg.open = False
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text("选择模型"),
                content=ft.Container(
                    content=ft.Column(
                        controls=model_tiles,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    height=400,
                    width=360,
                ),
                actions=[ft.TextButton("取消", on_click=close_dialog)],
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

            _show_snackbar(f"已加载 {len(models)} 个模型", ft.Colors.GREEN)

        except Exception as exc:
            _show_snackbar(f"加载模型失败: {str(exc)[:200]}", ft.Colors.RED)

    # --- Action buttons ---
    save_button = ft.ElevatedButton(
        "保存配置",
        icon=ft.Icons.SAVE,
        on_click=on_save_config,
    )

    test_button = ft.ElevatedButton(
        "测试连接",
        icon=ft.Icons.WIFI,
        on_click=on_test_connection,
    )

    load_models_button = ft.ElevatedButton(
        "加载模型列表",
        icon=ft.Icons.REFRESH,
        on_click=on_load_models,
    )

    # --- API config card ---
    api_config_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("API 配置", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "配置用于 AI 推理的 OpenAI 兼容 API",
                        color=ft.Colors.GREY,
                        size=13,
                    ),
                    ft.Divider(),
                    base_url_field,
                    api_key_field,
                    model_field,
                    load_models_button,
                    system_prompt_field,
                    ft.Row(
                        controls=[save_button, test_button],
                        spacing=15,
                    ),
                ],
                spacing=12,
            ),
            padding=20,
            width=700,
        ),
    )

    # --- Danger zone (only if a project is loaded) ---
    danger_zone_controls: list[ft.Control] = []

    if app_state.current_project:
        proj_name = app_state.current_project.name
        proj_id = app_state.current_project.id

        def on_delete_project(e):
            """Show two-step deletion confirmation dialog."""
            confirm_input = ft.TextField(
                label=f"请输入项目名称「{proj_name}」以确认",
                hint_text=proj_name,
            )
            error_label = ft.Text("", color=ft.Colors.RED)

            def do_delete(e):
                if confirm_input.value.strip() != proj_name:
                    error_label.value = "项目名称不匹配，请重新输入"
                    page.update()
                    return
                app_state.delete_project(proj_id)
                dlg.open = False
                page.update()
                _show_snackbar(f"项目「{proj_name}」已删除", ft.Colors.GREEN)

            def close_dlg(e):
                dlg.open = False
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text("⚠️ 确认删除项目", color=ft.Colors.RED),
                content=ft.Column(
                    controls=[
                        ft.Text(f"您确定要永久删除项目「{proj_name}」吗？"),
                        ft.Text(
                            "此操作将删除所有人物、地点、剧本、事实和推断数据，且无法恢复。",
                            color=ft.Colors.RED,
                            size=13,
                        ),
                        confirm_input,
                        error_label,
                    ],
                    tight=True,
                    spacing=10,
                ),
                actions=[
                    ft.TextButton("取消", on_click=close_dlg),
                    ft.ElevatedButton(
                        "永久删除",
                        icon=ft.Icons.DELETE_FOREVER,
                        color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.RED,
                        on_click=do_delete,
                    ),
                ],
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        danger_zone_controls = [
            ft.Divider(height=30),
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "⚠️ 危险操作",
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.RED,
                        ),
                        ft.Text(
                            "以下操作不可撤销，请谨慎操作",
                            color=ft.Colors.GREY,
                            size=13,
                        ),
                        ft.Container(height=10),
                        ft.ElevatedButton(
                            "删除此项目",
                            icon=ft.Icons.DELETE_FOREVER,
                            color=ft.Colors.WHITE,
                            bgcolor=ft.Colors.RED,
                            on_click=on_delete_project,
                        ),
                    ],
                    spacing=8,
                ),
                border=ft.Border.all(1, ft.Colors.RED),
                border_radius=10,
                padding=20,
                width=700,
            ),
        ]

    # --- Assemble the full settings page ---
    return ft.Column(
        controls=[
            ft.Text("设置", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            api_config_card,
            *danger_zone_controls,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        expand=True,
    )
