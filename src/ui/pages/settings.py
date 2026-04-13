"""设置页面 — Settings tab.

API configuration: base URL, key, model, system prompt override.
Model list loading with selection dialog.
Project management: delete project.
"""

from nicegui import ui

from src.services.config import load_config, save_config
from src.ui.state import app_state


def settings_tab_content():
    """Render the settings tab content."""
    config = load_config()

    with ui.column().classes("w-full q-pa-md gap-4"):
        ui.label("设置").classes("text-h5")

        with ui.card().classes("w-full max-w-2xl"):
            with ui.card_section():
                ui.label("API 配置").classes("text-h6")
                ui.label("配置用于 AI 推理的 OpenAI 兼容 API").classes(
                    "text-body2 text-grey"
                )

            with ui.card_section():
                base_url_input = ui.input(
                    label="API Base URL",
                    value=config.get("api_base_url", ""),
                    placeholder="https://api.openai.com/v1",
                ).classes("w-full")

                api_key_input = ui.input(
                    label="API Key（部分服务商可留空）",
                    value=config.get("api_key", ""),
                    placeholder="sk-...（Ollama 等本地服务可留空）",
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")

                # --- Model input with optional model list dialog ---
                model_input = ui.input(
                    label="模型名称",
                    value=config.get("model", ""),
                    placeholder="gpt-4o / deepseek-chat / llama3",
                ).classes("w-full")

                # --- Load Models button (A2.2) ---
                async def do_load_models():
                    """Fetch model list from API and show a selection dialog."""
                    base_url = base_url_input.value.strip()
                    if not base_url:
                        ui.notify("请先填写 API Base URL", type="warning")
                        return

                    # Temporarily save config so LLMService can read it
                    temp_config = {
                        "api_base_url": base_url,
                        "api_key": api_key_input.value.strip(),
                        "model": model_input.value.strip() or "",
                        "system_prompt_override": "",
                    }
                    save_config(temp_config)

                    spinner = ui.spinner("dots", size="lg", color="primary")
                    ui.notify("正在加载模型列表...", type="info")
                    try:
                        from src.services.llm_service import LLMService

                        llm = LLMService()
                        models = await llm.list_models()
                        if models:
                            with ui.dialog() as dlg, ui.card().classes("w-96"):
                                ui.label("选择模型").classes("text-h6 q-mb-md")
                                with ui.scroll_area().classes("max-h-96"):
                                    for m in models:
                                        def make_handler(name):
                                            def handler():
                                                model_input.value = name
                                                dlg.close()
                                            return handler
                                        ui.item(m, on_click=make_handler(m)).classes(
                                            "cursor-pointer"
                                        )
                                with ui.row().classes("w-full justify-end q-mt-sm"):
                                    ui.button("取消", on_click=dlg.close).props("flat")
                            dlg.open()
                            ui.notify(
                                f"已加载 {len(models)} 个模型",
                                type="positive",
                            )
                        else:
                            ui.notify("未发现可用模型", type="warning")
                    except Exception as e:
                        ui.notify(
                            f"加载模型失败: {str(e)[:200]}",
                            type="negative",
                            timeout=10000,
                        )
                    finally:
                        spinner.delete()

                ui.button(
                    "加载模型列表",
                    on_click=do_load_models,
                    icon="refresh",
                ).props("outline dense").classes("q-mt-xs")

                prompt_input = ui.textarea(
                    label="自定义系统提示词（可选）",
                    value=config.get("system_prompt_override", ""),
                    placeholder="覆盖默认的系统提示词。留空则使用内置提示词。",
                ).classes("w-full").props("rows=5")

            with ui.card_section():
                with ui.row().classes("gap-4"):
                    def do_save():
                        new_config = {
                            "api_base_url": base_url_input.value.strip(),
                            "api_key": api_key_input.value.strip(),
                            "model": model_input.value.strip(),
                            "system_prompt_override": prompt_input.value.strip(),
                        }
                        save_config(new_config)
                        ui.notify("配置已保存", type="positive")

                    ui.button("保存配置", on_click=do_save, icon="save").props(
                        "color=primary"
                    )

                    async def do_test():
                        base_url = base_url_input.value.strip()
                        model = model_input.value.strip()

                        # Only base_url is required (A2.4)
                        if not base_url or not model:
                            ui.notify(
                                "请先填写 API Base URL 和模型名称",
                                type="warning",
                            )
                            return

                        # Save config first so LLMService can read it
                        temp_config = {
                            "api_base_url": base_url,
                            "api_key": api_key_input.value.strip(),
                            "model": model,
                            "system_prompt_override": prompt_input.value.strip(),
                        }
                        save_config(temp_config)

                        spinner = ui.spinner("dots", size="lg", color="primary")
                        ui.notify("正在测试连接...", type="info")
                        try:
                            from src.services.llm_service import LLMService

                            llm = LLMService()
                            reply = await llm.test_connection()
                            ui.notify(
                                f"连接成功！模型响应: {reply}",
                                type="positive",
                            )
                        except Exception as e:
                            ui.notify(
                                f"连接失败: {str(e)[:200]}",
                                type="negative",
                                timeout=10000,
                            )
                        finally:
                            spinner.delete()

                    ui.button("测试连接", on_click=do_test, icon="wifi").props(
                        "outline"
                    )

        # --- Project Danger Zone ---
        if app_state.current_project:
            ui.separator().classes("q-my-lg")
            with ui.card().classes("w-full max-w-2xl").style(
                "border: 1px solid #ff5252;"
            ):
                with ui.card_section():
                    ui.label("⚠️ 危险操作").classes("text-h6 text-negative")
                    ui.label("以下操作不可撤销，请谨慎操作").classes(
                        "text-body2 text-grey"
                    )

                with ui.card_section():
                    proj_name = app_state.current_project.name

                    def confirm_delete_project():
                        """Show a strong confirmation dialog for project deletion."""
                        with ui.dialog() as dlg, ui.card().classes("w-96"):
                            ui.label("⚠️ 确认删除项目").classes("text-h6 text-negative q-mb-md")
                            ui.label(
                                f"您确定要永久删除项目「{proj_name}」吗？"
                            ).classes("text-body1 q-mb-sm")
                            ui.label(
                                "此操作将删除所有人物、地点、剧本、事实和推断数据，且无法恢复。"
                            ).classes("text-body2 text-negative q-mb-md")

                            confirm_input = ui.input(
                                label=f'请输入项目名称「{proj_name}」以确认',
                                placeholder=proj_name,
                            ).classes("w-full")

                            error_label = ui.label("").classes("text-negative")

                            def do_delete():
                                if confirm_input.value.strip() != proj_name:
                                    error_label.text = "项目名称不匹配，请重新输入"
                                    return
                                proj_id = app_state.current_project.id
                                app_state.delete_project(proj_id)
                                ui.notify(f"项目「{proj_name}」已删除", type="positive")
                                dlg.close()

                            with ui.row().classes("w-full justify-end q-mt-md"):
                                ui.button("取消", on_click=dlg.close).props("flat")
                                ui.button(
                                    "永久删除",
                                    on_click=do_delete,
                                    icon="delete_forever",
                                ).props("color=negative")

                        dlg.open()

                    ui.button(
                        "删除此项目",
                        on_click=confirm_delete_project,
                        icon="delete_forever",
                    ).props("color=negative outline")
