"""自定义推理页面。"""

import flet as ft

from src.models.puzzle import EntityKind
from src.services.config import load_config
from src.ui.pages.matrix import _show_new_entities_dialog
from src.ui.state import app_state

_custom_tab_state: dict[str, dict[str, str | bool]] = {}


def build_custom_tab(page: ft.Page) -> ft.Control:
    """Build custom deduction tab content."""
    proj = app_state.current_project
    if not proj:
        return ft.Column(
            controls=[
                ft.Text("自定义推理", size=28, weight=ft.FontWeight.BOLD),
                ft.Text("请先选择或创建一个项目", color=ft.Colors.GREY),
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    outer_container = ft.Container(expand=True)

    def show_snackbar(message: str, color: str | None = None):
        page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def refresh():
        outer_container.content = _build_content(page, refresh, show_snackbar)
        page.update()

    outer_container.content = _build_content(page, refresh, show_snackbar)

    return ft.Column(
        controls=[
            ft.Text("自定义推理", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            outer_container,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        expand=True,
    )


def _is_api_configured() -> bool:
    cfg = load_config()
    return bool(cfg.get("api_base_url") and cfg.get("model"))


def _build_content(page: ft.Page, refresh, show_snackbar) -> ft.Control:
    proj = app_state.current_project
    if not proj:
        return ft.Text("请先选择或创建一个项目", color=ft.Colors.GREY)

    state = _custom_tab_state.setdefault(
        proj.id,
        {
            "custom_rules": "",
            "include_reasoning": True,
            "result_text": "",
        },
    )

    controls: list[ft.Control] = []

    if not _is_api_configured():
        controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.AMBER),
                        ft.Text(
                            "API 未配置，自定义推理暂不可用。请前往「设置」页面配置 API。",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=10,
                ),
                border=ft.Border.all(1, ft.Colors.AMBER),
                border_radius=8,
                padding=12,
                bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.AMBER),
            )
        )

    if not proj.scripts:
        controls.append(
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.DESCRIPTION, size=48, color=ft.Colors.GREY),
                            ft.Text("请先添加原始剧本", size=16, color=ft.Colors.GREY),
                            ft.Text(
                                "自定义推理只会使用原始剧本和你输入的规则。",
                                size=13,
                                color=ft.Colors.GREY,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    padding=30,
                    alignment=ft.Alignment.CENTER,
                ),
            )
        )
        return ft.Column(controls=controls, spacing=12)

    custom_rules_field = ft.TextField(
        label="附加自定义规则（可选）",
        hint_text="例如：凶手不可能在案发后 10 分钟内离开主楼；A 与 B 同一时段不在同一地点",
        multiline=True,
        min_lines=6,
        max_lines=12,
        value=str(state["custom_rules"]),
    )
    include_reasoning_switch = ft.Switch(
        label="输出精简解释",
        value=bool(state["include_reasoning"]),
    )
    result_text = ft.TextField(
        label="推理结果",
        multiline=True,
        min_lines=12,
        max_lines=24,
        read_only=True,
        value=str(state["result_text"]),
    )

    def sync_state():
        state["custom_rules"] = custom_rules_field.value or ""
        state["include_reasoning"] = include_reasoning_switch.value
        state["result_text"] = result_text.value or ""

    def on_rules_change(e):
        sync_state()

    def on_reasoning_change(e):
        sync_state()

    custom_rules_field.on_change = on_rules_change
    include_reasoning_switch.on_change = on_reasoning_change

    async def run_custom_deduction(e):
        rules_text = (custom_rules_field.value or "").strip()

        if not _is_api_configured():
            show_snackbar("请先配置 API", ft.Colors.RED)
            return

        result_text.value = "正在推理，请稍候..."
        sync_state()
        page.update()

        try:
            from src.services.deduction import DeductionService

            service = DeductionService()
            result = await service.run_custom_deduction(
                proj,
                custom_rules_text=rules_text,
                include_reasoning=include_reasoning_switch.value,
                ts_by_id=app_state.cache.ts_by_id,
            )
            result_text.value = _format_custom_result(
                result,
                include_reasoning=include_reasoning_switch.value,
            )
            sync_state()
            page.update()

            existing_char_names = {c.name for c in proj.characters}
            existing_loc_names = {lo.name for lo in proj.locations}
            final_unknown_chars = [
                n
                for n in result.get("new_characters_detected", [])
                if n.get("name")
                and n["name"] not in existing_char_names
                and not app_state.is_entity_ignored(EntityKind.character, n["name"])
            ]
            final_unknown_locs = [
                n
                for n in result.get("new_locations_detected", [])
                if n.get("name")
                and n["name"] not in existing_loc_names
                and not app_state.is_entity_ignored(EntityKind.location, n["name"])
            ]

            if final_unknown_chars or final_unknown_locs:
                show_snackbar("自定义推理完成，发现新实体，请确认是否添加。", ft.Colors.GREEN)
                _show_new_entities_dialog(
                    page,
                    final_unknown_chars,
                    final_unknown_locs,
                    run_custom_deduction,
                    refresh,
                    show_snackbar,
                )
            else:
                show_snackbar("自定义推理完成", ft.Colors.GREEN)
        except ValueError as exc:
            result_text.value = ""
            sync_state()
            page.update()
            show_snackbar(str(exc), ft.Colors.RED)
        except Exception as exc:
            result_text.value = ""
            sync_state()
            page.update()
            show_snackbar(f"自定义推理失败: {str(exc)[:200]}", ft.Colors.RED)

    controls.extend(
        [
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "使用原始剧本 + 管理中的规则 + 附加自定义规则",
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "该页面不会写入待审查推断，也不会与其它推理结果混在一起。",
                                size=13,
                                color=ft.Colors.GREY,
                            ),
                            ft.Text(
                                f"当前将自动带上管理中的规则/提示/约束：{len(proj.hints)} 条",
                                size=13,
                                color=ft.Colors.GREY,
                            ),
                            custom_rules_field,
                            include_reasoning_switch,
                            ft.Row(
                                controls=[
                                    ft.ElevatedButton(
                                        "开始自定义推理",
                                        icon=ft.Icons.PSYCHOLOGY,
                                        on_click=run_custom_deduction
                                        if _is_api_configured()
                                        else None,
                                        disabled=not _is_api_configured(),
                                    ),
                                    ft.OutlinedButton(
                                        "清空结果",
                                        on_click=lambda e: _clear_result(
                                            proj.id,
                                            custom_rules_field,
                                            include_reasoning_switch,
                                            result_text,
                                            page,
                                        ),
                                    ),
                                ],
                                spacing=10,
                            ),
                        ],
                        spacing=12,
                    ),
                    padding=20,
                )
            ),
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        controls=[result_text],
                        spacing=10,
                    ),
                    padding=20,
                )
            ),
        ]
    )

    return ft.Column(controls=controls, spacing=12)


def _clear_result(
    project_id: str,
    custom_rules_field: ft.TextField,
    include_reasoning_switch: ft.Switch,
    result_text: ft.TextField,
    page: ft.Page,
) -> None:
    _custom_tab_state[project_id] = {
        "custom_rules": custom_rules_field.value or "",
        "include_reasoning": include_reasoning_switch.value,
        "result_text": "",
    }
    result_text.value = ""
    page.update()


def _format_custom_result(result: dict, include_reasoning: bool) -> str:
    answers = result.get("answers") or []
    summary = (result.get("summary") or "").strip()

    lines: list[str] = []
    if summary:
        lines.append(f"整体结论：{summary}")
        lines.append("")

    if not answers:
        lines.append("未得到明确的可能答案。")
        return "\n".join(lines)

    lines.append("可能有效的答案：")
    for idx, answer in enumerate(answers, start=1):
        confidence = answer.get("confidence", "medium")
        answer_text = (answer.get("answer_text") or "").strip()
        character_id = (answer.get("character_id") or "").strip()
        location_id = (answer.get("location_id") or "").strip()
        time_slot = (answer.get("time_slot") or "").strip()
        explanation = (answer.get("explanation") or "").strip()

        parts = [f"{idx}. [{confidence}]"]
        if answer_text:
            parts.append(answer_text)
        mapped_parts = [p for p in [character_id, location_id, time_slot] if p]
        if mapped_parts:
            parts.append(f"({', '.join(mapped_parts)})")
        lines.append(" ".join(parts).strip())

        if include_reasoning and explanation:
            lines.append(f"   - 解释：{explanation}")

    return "\n".join(lines)
