"""实体管理页面 — Manage tab (Flet version).

Sections: 时间管理, 人物管理, 地点管理, 游戏规则, 手动添加事实.
"""

import re

import flet as ft
from loguru import logger

from src.models.puzzle import CharacterStatus, HintType, SourceType
from src.ui.state import app_state


def build_manage_tab(page: ft.Page) -> ft.Control:
    """Build and return the entity management tab control tree.

    Contains 5 ExpansionPanel sections:
    - 🕐 时间管理: time slot chips with add/delete
    - 👤 人物管理: character cards with edit/delete dialogs
    - 📍 地点管理: location cards with edit/delete dialogs
    - 📋 游戏规则: hints/rules/constraints with add/delete
    - ✅ 手动添加事实: fact entry form + fact list
    """

    # Outer container holding the panel list — replaced on refresh
    outer_container = ft.Container(expand=True)

    def _show_snackbar(message: str, color: str | None = None):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=color,
        )
        page.snack_bar.open = True
        page.update()

    def refresh():
        """Rebuild the entire manage tab content after state changes."""
        outer_container.content = _build_content(page, refresh, _show_snackbar)
        page.update()

    outer_container.content = _build_content(page, refresh, _show_snackbar)
    return ft.Column(
        controls=[
            ft.Text("管理", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            outer_container,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        expand=True,
    )


def _build_content(page: ft.Page, refresh, show_snackbar) -> ft.Control:
    """Build all 5 expansion panel sections."""
    if not app_state.current_project:
        return ft.Text("请先选择或创建一个项目", color=ft.Colors.GREY, size=16)

    proj = app_state.current_project

    # Quick-start guidance
    guidance_controls: list[ft.Control] = []
    if not proj.characters and not proj.locations and not proj.time_slots:
        guidance_controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("🚀 快速开始", size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "推荐先在「剧本」页面添加剧本，AI 将自动提取人物、地点和时间段。",
                            size=14,
                        ),
                        ft.Text("1️⃣ 前往「剧本」页面 — 粘贴剧本文本并保存", size=13),
                        ft.Text("2️⃣ AI 自动分析 — 提取人物、地点、时间段和事实", size=13),
                        ft.Text("3️⃣ 审核结果 — 在「审查」页面确认 AI 提取的推断", size=13),
                        ft.Text("4️⃣ 手动补充 — 在此页面管理和微调实体信息", size=13),
                    ],
                    spacing=6,
                ),
                border=ft.Border.all(1, ft.Colors.BLUE_200),
                border_radius=10,
                padding=20,
                margin=ft.Margin.only(bottom=15),
            )
        )

    panel_list = ft.ExpansionPanelList(
        elevation=2,
        controls=[
            _build_time_slots_panel(page, refresh, show_snackbar),
            _build_characters_panel(page, refresh, show_snackbar),
            _build_locations_panel(page, refresh, show_snackbar),
            _build_hints_panel(page, refresh, show_snackbar),
            _build_facts_panel(page, refresh, show_snackbar),
        ],
    )

    return ft.Column(
        controls=[
            *guidance_controls,
            panel_list,
        ],
        spacing=10,
    )


# =============================================================================
# 1. 🕐 时间管理
# =============================================================================


def _build_time_slots_panel(page, refresh, show_snackbar) -> ft.ExpansionPanel:
    """Time slot management panel."""
    proj = app_state.current_project
    slots = sorted(proj.time_slots, key=lambda ts: ts.sort_order) if proj else []

    ts_input = ft.TextField(
        label="时间",
        hint_text="HH:MM，例如 14:00",
        width=160,
        dense=True,
    )
    desc_input = ft.TextField(
        label="描述（可选）",
        hint_text="例如 第一天",
        width=200,
        dense=True,
    )

    def on_remove_slot(ts):
        chip_text = f"{ts.label}({ts.description})" if ts.description else ts.label
        logger.info("manage: remove_time_slot id={!r} label={!r}", ts.id, ts.label)
        app_state.remove_time_slot(ts.id)
        show_snackbar(f"已删除时间段 {chip_text}", ft.Colors.GREEN)
        refresh()

    def on_reorder_slot(ts, direction):
        app_state.reorder_time_slot(ts.id, direction)
        refresh()

    def on_add_slot(e):
        val = ts_input.value.strip()
        desc = desc_input.value.strip() if desc_input.value else ""
        if not val:
            show_snackbar("请输入时间", ft.Colors.AMBER)
            return
        if not re.match(r"^\d{2}:\d{2}$", val):
            show_snackbar("格式错误，请使用 HH:MM 格式", ft.Colors.RED)
            return
        try:
            added = app_state.add_time_slot(val, description=desc)
        except ValueError as exc:
            show_snackbar(str(exc), ft.Colors.RED)
            return
        if added:
            logger.info("manage: add_time_slot {!r} desc={!r}", val, desc)
            show_snackbar(f"已添加时间段 {val}", ft.Colors.GREEN)
            ts_input.value = ""
            desc_input.value = ""
            refresh()
        else:
            show_snackbar(f"时间段 {val} 已存在", ft.Colors.AMBER)

    # Build chips
    chip_controls: list[ft.Control] = []
    if not slots:
        chip_controls.append(ft.Text("暂无时间段，请添加", color=ft.Colors.GREY, size=13))
    else:
        for ts in slots:
            chip_text = f"{ts.label}({ts.description})" if ts.description else ts.label

            def make_delete_handler(slot=ts):
                return lambda e: on_remove_slot(slot)

            def make_up_handler(slot=ts):
                return lambda e: on_reorder_slot(slot, -1)

            def make_down_handler(slot=ts):
                return lambda e: on_reorder_slot(slot, 1)

            chip_controls.append(
                ft.Row(
                    controls=[
                        ft.Chip(
                            label=ft.Text(chip_text),
                            delete_icon_color=ft.Colors.RED,
                            on_delete=make_delete_handler(ts),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_UPWARD,
                            on_click=make_up_handler(ts),
                            icon_size=16,
                            tooltip="上移",
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_DOWNWARD,
                            on_click=make_down_handler(ts),
                            icon_size=16,
                            tooltip="下移",
                        ),
                    ],
                    spacing=0,
                )
            )

    return ft.ExpansionPanel(
        expanded=True,
        header=ft.ListTile(title=ft.Text("🕐 时间管理")),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(controls=chip_controls, wrap=True, spacing=8),
                    ft.Divider(),
                    ft.Row(
                        controls=[
                            ts_input,
                            desc_input,
                            ft.ElevatedButton("添加", icon=ft.Icons.ADD, on_click=on_add_slot),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=12,
            ),
            padding=ft.Padding.only(left=15, right=15, bottom=15),
        ),
    )


# =============================================================================
# 2. 👤 人物管理
# =============================================================================


def _status_label(status: CharacterStatus) -> str:
    return {"confirmed": "已确认", "suspected": "疑似", "unknown": "未知"}.get(
        status.value, status.value
    )


def _status_color(status: CharacterStatus) -> str:
    return {
        "confirmed": ft.Colors.GREEN,
        "suspected": ft.Colors.ORANGE,
        "unknown": ft.Colors.GREY,
    }.get(status.value, ft.Colors.GREY)


def _build_characters_panel(page, refresh, show_snackbar) -> ft.ExpansionPanel:
    """Character management panel."""
    proj = app_state.current_project
    chars = proj.characters if proj else []

    def show_character_dialog(
        title: str = "人物",
        initial_name: str = "",
        initial_aliases: str = "",
        initial_desc: str = "",
        initial_status: str = "confirmed",
        on_save=None,
    ):
        name_field = ft.TextField(label="姓名 *", value=initial_name, autofocus=True)
        aliases_field = ft.TextField(
            label="别名（逗号分隔）",
            value=initial_aliases,
            hint_text="张三, 小张",
        )
        desc_field = ft.TextField(label="描述（可选）", value=initial_desc)
        status_options = [
            ft.dropdown.Option(key="confirmed", text="已确认"),
            ft.dropdown.Option(key="suspected", text="疑似"),
            ft.dropdown.Option(key="unknown", text="未知"),
        ]
        status_dropdown = ft.Dropdown(
            label="状态",
            value=initial_status,
            options=status_options,
            width=200,
        )
        error_text = ft.Text("", color=ft.Colors.RED)

        def do_save(e):
            name = name_field.value.strip()
            if not name:
                error_text.value = "姓名不能为空"
                page.update()
                return
            if on_save:
                on_save(name, aliases_field.value, desc_field.value.strip(), status_dropdown.value)
            dlg.open = False
            page.update()

        def do_cancel(e):
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Column(
                controls=[name_field, aliases_field, desc_field, status_dropdown, error_text],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("取消", on_click=do_cancel),
                ft.ElevatedButton("保存", on_click=do_save),
            ],
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def on_add_character(e):
        def do_add(name, aliases_str, desc, status_val):
            aliases = (
                [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
            )
            logger.info("manage: add_character name={!r}", name)
            app_state.add_character(
                name=name,
                aliases=aliases,
                description=desc or None,
                status=CharacterStatus(status_val),
            )
            show_snackbar("人物已添加", ft.Colors.GREEN)
            refresh()

        show_character_dialog(title="添加人物", on_save=do_add)

    def make_edit_handler(char):
        def handler(e):
            def do_update(name, aliases_str, desc, status_val):
                aliases = (
                    [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
                )
                logger.info("manage: update_character id={!r} name={!r}", char.id, name)
                app_state.update_character(
                    char.id,
                    name=name,
                    aliases=aliases,
                    description=desc or None,
                    status=CharacterStatus(status_val),
                )
                show_snackbar("人物已更新", ft.Colors.GREEN)
                refresh()

            show_character_dialog(
                title="编辑人物",
                initial_name=char.name,
                initial_aliases=", ".join(char.aliases),
                initial_desc=char.description or "",
                initial_status=char.status.value,
                on_save=do_update,
            )

        return handler

    def make_delete_handler(char):
        def handler(e):
            def do_delete(e):
                logger.info("manage: remove_character id={!r} name={!r}", char.id, char.name)
                app_state.remove_character(char.id)
                show_snackbar("删除成功", ft.Colors.GREEN)
                dlg.open = False
                page.update()
                refresh()

            def do_cancel(e):
                dlg.open = False
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text(f"确认删除人物「{char.name}」？"),
                content=ft.Text("此操作不可撤销"),
                actions=[
                    ft.TextButton("取消", on_click=do_cancel),
                    ft.ElevatedButton(
                        "删除", color=ft.Colors.WHITE, bgcolor=ft.Colors.RED, on_click=do_delete
                    ),
                ],
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        return handler

    # Build character cards
    char_controls: list[ft.Control] = []
    if not chars:
        char_controls.append(ft.Text("暂无人物，请添加", color=ft.Colors.GREY, size=13))
    else:
        for c in chars:
            alias_text = (
                ft.Text(f"别名: {', '.join(c.aliases)}", size=12, color=ft.Colors.GREY)
                if c.aliases
                else ft.Container()
            )
            desc_text = (
                ft.Text(c.description, size=13, color=ft.Colors.GREY)
                if c.description
                else ft.Container()
            )

            status_badge = ft.Container(
                content=ft.Text(_status_label(c.status), size=11, color=ft.Colors.WHITE),
                bgcolor=_status_color(c.status),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            )

            card = ft.Card(
                content=ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Text(c.name, size=16, weight=ft.FontWeight.BOLD),
                                            status_badge,
                                        ],
                                        spacing=10,
                                    ),
                                    alias_text,
                                    desc_text,
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.Row(
                                controls=[
                                    ft.IconButton(
                                        icon=ft.Icons.EDIT,
                                        on_click=make_edit_handler(c),
                                        tooltip="编辑",
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE,
                                        icon_color=ft.Colors.RED,
                                        on_click=make_delete_handler(c),
                                        tooltip="删除",
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=15,
                ),
                width=320,
            )
            char_controls.append(card)

    char_controls.append(
        ft.ElevatedButton("添加人物", icon=ft.Icons.PERSON_ADD, on_click=on_add_character),
    )

    # Separate add button from cards for layout
    card_items = [c for c in char_controls if isinstance(c, ft.Card)]
    non_card_items = [c for c in char_controls if not isinstance(c, ft.Card)]

    content_controls: list[ft.Control] = []
    if card_items:
        content_controls.append(ft.Row(controls=card_items, wrap=True, spacing=8, run_spacing=8))
    content_controls.extend(non_card_items)

    return ft.ExpansionPanel(
        expanded=True,
        header=ft.ListTile(title=ft.Text("👤 人物管理")),
        content=ft.Container(
            content=ft.Column(controls=content_controls, spacing=8),
            padding=ft.Padding.only(left=15, right=15, bottom=15),
        ),
    )


# =============================================================================
# 3. 📍 地点管理
# =============================================================================


def _build_locations_panel(page, refresh, show_snackbar) -> ft.ExpansionPanel:
    """Location management panel."""
    proj = app_state.current_project
    locs = proj.locations if proj else []

    def show_location_dialog(
        title: str = "地点",
        initial_name: str = "",
        initial_aliases: str = "",
        initial_desc: str = "",
        on_save=None,
    ):
        name_field = ft.TextField(label="名称 *", value=initial_name, autofocus=True)
        aliases_field = ft.TextField(
            label="别名（逗号分隔）",
            value=initial_aliases,
            hint_text="图书馆, Library",
        )
        desc_field = ft.TextField(label="描述（可选）", value=initial_desc)
        error_text = ft.Text("", color=ft.Colors.RED)

        def do_save(e):
            name = name_field.value.strip()
            if not name:
                error_text.value = "名称不能为空"
                page.update()
                return
            if on_save:
                on_save(name, aliases_field.value, desc_field.value.strip())
            dlg.open = False
            page.update()

        def do_cancel(e):
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Column(
                controls=[name_field, aliases_field, desc_field, error_text],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("取消", on_click=do_cancel),
                ft.ElevatedButton("保存", on_click=do_save),
            ],
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def on_add_location(e):
        def do_add(name, aliases_str, desc):
            aliases = (
                [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
            )
            logger.info("manage: add_location name={!r}", name)
            app_state.add_location(
                name=name,
                aliases=aliases,
                description=desc or None,
            )
            show_snackbar("地点已添加", ft.Colors.GREEN)
            refresh()

        show_location_dialog(title="添加地点", on_save=do_add)

    def make_edit_handler(loc):
        def handler(e):
            def do_update(name, aliases_str, desc):
                aliases = (
                    [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
                )
                logger.info("manage: update_location id={!r} name={!r}", loc.id, name)
                app_state.update_location(
                    loc.id,
                    name=name,
                    aliases=aliases,
                    description=desc or None,
                )
                show_snackbar("地点已更新", ft.Colors.GREEN)
                refresh()

            show_location_dialog(
                title="编辑地点",
                initial_name=loc.name,
                initial_aliases=", ".join(loc.aliases),
                initial_desc=loc.description or "",
                on_save=do_update,
            )

        return handler

    def make_delete_handler(loc):
        def handler(e):
            def do_delete(e):
                logger.info("manage: remove_location id={!r} name={!r}", loc.id, loc.name)
                app_state.remove_location(loc.id)
                show_snackbar("删除成功", ft.Colors.GREEN)
                dlg.open = False
                page.update()
                refresh()

            def do_cancel(e):
                dlg.open = False
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text(f"确认删除地点「{loc.name}」？"),
                content=ft.Text("此操作不可撤销"),
                actions=[
                    ft.TextButton("取消", on_click=do_cancel),
                    ft.ElevatedButton(
                        "删除", color=ft.Colors.WHITE, bgcolor=ft.Colors.RED, on_click=do_delete
                    ),
                ],
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        return handler

    # Build location cards
    loc_controls: list[ft.Control] = []
    if not locs:
        loc_controls.append(ft.Text("暂无地点，请添加", color=ft.Colors.GREY, size=13))
    else:
        for loc in locs:
            alias_text = (
                ft.Text(f"别名: {', '.join(loc.aliases)}", size=12, color=ft.Colors.GREY)
                if loc.aliases
                else ft.Container()
            )
            desc_text = (
                ft.Text(loc.description, size=13, color=ft.Colors.GREY)
                if loc.description
                else ft.Container()
            )

            card = ft.Card(
                content=ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(loc.name, size=16, weight=ft.FontWeight.BOLD),
                                    alias_text,
                                    desc_text,
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.Row(
                                controls=[
                                    ft.IconButton(
                                        icon=ft.Icons.EDIT,
                                        on_click=make_edit_handler(loc),
                                        tooltip="编辑",
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE,
                                        icon_color=ft.Colors.RED,
                                        on_click=make_delete_handler(loc),
                                        tooltip="删除",
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=15,
                ),
                width=320,
            )
            loc_controls.append(card)

    loc_controls.append(
        ft.ElevatedButton("添加地点", icon=ft.Icons.ADD_LOCATION, on_click=on_add_location),
    )

    # Separate add button from cards for layout
    loc_card_items = [c for c in loc_controls if isinstance(c, ft.Card)]
    loc_non_card_items = [c for c in loc_controls if not isinstance(c, ft.Card)]

    loc_content_controls: list[ft.Control] = []
    if loc_card_items:
        loc_content_controls.append(
            ft.Row(controls=loc_card_items, wrap=True, spacing=8, run_spacing=8)
        )
    loc_content_controls.extend(loc_non_card_items)

    return ft.ExpansionPanel(
        expanded=True,
        header=ft.ListTile(title=ft.Text("📍 地点管理")),
        content=ft.Container(
            content=ft.Column(controls=loc_content_controls, spacing=8),
            padding=ft.Padding.only(left=15, right=15, bottom=15),
        ),
    )


# =============================================================================
# 4. 📋 游戏规则
# =============================================================================


def _hint_type_label(ht: HintType) -> str:
    return {"rule": "规则", "hint": "提示", "constraint": "约束"}.get(ht.value, ht.value)


def _hint_type_color(ht: HintType) -> str:
    return {"rule": ft.Colors.BLUE, "hint": ft.Colors.TEAL, "constraint": ft.Colors.ORANGE}.get(
        ht.value, ft.Colors.GREY
    )


def _build_hints_panel(page, refresh, show_snackbar) -> ft.ExpansionPanel:
    """Hints/rules/constraints management panel."""
    proj = app_state.current_project
    hints = proj.hints if proj else []

    def make_delete_handler(hint):
        def handler(e):
            logger.info("manage: remove_hint id={!r}", hint.id)
            app_state.remove_hint(hint.id)
            show_snackbar("删除成功", ft.Colors.GREEN)
            refresh()

        return handler

    def on_add_hint(e):
        type_dropdown = ft.Dropdown(
            label="类型",
            value="rule",
            options=[
                ft.dropdown.Option(key="rule", text="规则 (Rule)"),
                ft.dropdown.Option(key="hint", text="提示 (Hint)"),
                ft.dropdown.Option(key="constraint", text="约束 (Constraint)"),
            ],
            width=250,
        )
        content_field = ft.TextField(
            label="内容 *",
            hint_text="例如：每个人每个时间段只能在一个地点",
            multiline=True,
            min_lines=3,
        )
        error_text = ft.Text("", color=ft.Colors.RED)

        def do_save(e):
            content = content_field.value.strip()
            if not content:
                error_text.value = "内容不能为空"
                page.update()
                return
            logger.info("manage: add_hint type={!r}", type_dropdown.value)
            app_state.add_hint(
                hint_type=HintType(type_dropdown.value),
                content=content,
            )
            show_snackbar("规则已添加", ft.Colors.GREEN)
            dlg.open = False
            page.update()
            refresh()

        def do_cancel(e):
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("添加规则"),
            content=ft.Column(
                controls=[type_dropdown, content_field, error_text],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("取消", on_click=do_cancel),
                ft.ElevatedButton("保存", on_click=do_save),
            ],
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    # Build hint cards
    hint_controls: list[ft.Control] = []
    if not hints:
        hint_controls.append(ft.Text("暂无规则或提示，请添加", color=ft.Colors.GREY, size=13))
    else:
        for h in hints:
            type_badge = ft.Container(
                content=ft.Text(_hint_type_label(h.type), size=11, color=ft.Colors.WHITE),
                bgcolor=_hint_type_color(h.type),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            )

            card = ft.Card(
                content=ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    type_badge,
                                    ft.Text(h.content, size=14),
                                ],
                                spacing=10,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE,
                                icon_color=ft.Colors.RED,
                                on_click=make_delete_handler(h),
                                tooltip="删除",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=15,
                ),
            )
            hint_controls.append(card)

    hint_controls.append(
        ft.ElevatedButton("添加规则", icon=ft.Icons.ADD, on_click=on_add_hint),
    )

    return ft.ExpansionPanel(
        expanded=True,
        header=ft.ListTile(title=ft.Text("📋 游戏规则")),
        content=ft.Container(
            content=ft.Column(controls=hint_controls, spacing=8),
            padding=ft.Padding.only(left=15, right=15, bottom=15),
        ),
    )


# =============================================================================
# 5. ✅ 手动添加事实
# =============================================================================


def _source_type_label(st: SourceType) -> str:
    return {
        "script_explicit": "剧本明示",
        "user_input": "手动输入",
        "ai_deduction": "AI推断",
        "game_hint": "游戏提示",
    }.get(st.value, st.value)


def _build_facts_panel(page, refresh, show_snackbar) -> ft.ExpansionPanel:
    """Manual fact entry + existing facts list panel."""
    proj = app_state.current_project
    chars = proj.characters if proj else []
    locs = proj.locations if proj else []
    slots = sorted(proj.time_slots, key=lambda ts: ts.sort_order) if proj else []
    facts = proj.facts if proj else []

    form_controls: list[ft.Control] = []

    if not chars or not locs or not slots:
        form_controls.append(
            ft.Text("请先添加人物、地点和时间段后再录入事实", color=ft.Colors.GREY, size=13),
        )
    else:
        char_dropdown = ft.Dropdown(
            label="人物 *",
            options=[ft.dropdown.Option(key=c.id, text=c.name) for c in chars],
            width=180,
        )
        loc_dropdown = ft.Dropdown(
            label="地点 *",
            options=[ft.dropdown.Option(key=lo.id, text=lo.name) for lo in locs],
            width=180,
        )
        slot_dropdown = ft.Dropdown(
            label="时间段 *",
            options=[
                ft.dropdown.Option(
                    key=ts.id,
                    text=f"{ts.label}({ts.description})" if ts.description else ts.label,
                )
                for ts in slots
            ],
            width=180,
        )
        evidence_field = ft.TextField(
            label="证据/备注",
            hint_text="来源说明",
            expand=True,
        )

        def on_add_fact(e):
            if not char_dropdown.value:
                show_snackbar("请选择人物", ft.Colors.AMBER)
                return
            if not loc_dropdown.value:
                show_snackbar("请选择地点", ft.Colors.AMBER)
                return
            if not slot_dropdown.value:
                show_snackbar("请选择时间段", ft.Colors.AMBER)
                return
            # Check for duplicate
            existing = any(
                f.character_id == char_dropdown.value
                and f.location_id == loc_dropdown.value
                and f.time_slot == slot_dropdown.value
                for f in proj.facts
            )
            if existing:
                show_snackbar("该事实已存在，无需重复添加", ft.Colors.AMBER)
                return
            logger.info(
                "manage: add_fact char={!r} loc={!r} ts={!r}",
                char_dropdown.value,
                loc_dropdown.value,
                slot_dropdown.value,
            )
            app_state.add_fact(
                character_id=char_dropdown.value,
                location_id=loc_dropdown.value,
                time_slot=slot_dropdown.value,
                source_type=SourceType.user_input,
                source_evidence=evidence_field.value.strip() or None,
            )
            show_snackbar("事实已添加", ft.Colors.GREEN)
            refresh()

        form_controls.append(
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    char_dropdown,
                                    loc_dropdown,
                                    slot_dropdown,
                                    evidence_field,
                                ],
                                spacing=10,
                                wrap=True,
                            ),
                            ft.ElevatedButton("添加事实", icon=ft.Icons.ADD, on_click=on_add_fact),
                        ],
                        spacing=10,
                    ),
                    padding=15,
                ),
            ),
        )

    # Build fact list
    fact_controls: list[ft.Control] = []
    if not facts:
        fact_controls.append(ft.Text("暂无事实记录", color=ft.Colors.GREY, size=13))
    else:
        char_map = {c.id: c.name for c in chars}
        loc_map = {lo.id: lo.name for lo in locs}

        fact_controls.append(
            ft.Text(f"已有 {len(facts)} 条事实", size=14, weight=ft.FontWeight.BOLD)
        )
        fact_controls.append(ft.Divider())

        for f in facts:
            char_name = char_map.get(f.character_id, f.character_id[:8])
            loc_name = loc_map.get(f.location_id, f.location_id[:8])
            source_label = _source_type_label(f.source_type)

            def make_fact_delete_handler(fact=f):
                def handler(e):
                    def do_delete(e):
                        logger.info("manage: remove_fact id={!r}", fact.id)
                        app_state.remove_fact(fact.id)
                        show_snackbar("删除成功", ft.Colors.GREEN)
                        dlg.open = False
                        page.update()
                        refresh()

                    def do_cancel(e):
                        dlg.open = False
                        page.update()

                    dlg = ft.AlertDialog(
                        title=ft.Text("确认删除此事实？"),
                        content=ft.Text("此操作不可撤销"),
                        actions=[
                            ft.TextButton("取消", on_click=do_cancel),
                            ft.ElevatedButton(
                                "删除",
                                color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.RED,
                                on_click=do_delete,
                            ),
                        ],
                    )
                    page.overlay.append(dlg)
                    dlg.open = True
                    page.update()

                return handler

            ts_obj = app_state.get_time_slot_by_id(f.time_slot)
            ts_display = (
                (f"{ts_obj.label}({ts_obj.description})" if ts_obj.description else ts_obj.label)
                if ts_obj
                else f.time_slot
            )
            time_badge = ft.Container(
                content=ft.Text(ts_display, size=11, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.BLUE,
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            )
            source_badge = ft.Container(
                content=ft.Text(source_label, size=11, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.GREY,
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            )

            evidence_controls: list[ft.Control] = []
            if f.source_evidence:
                evidence_controls.append(
                    ft.Icon(
                        ft.Icons.INFO_OUTLINE,
                        size=18,
                        color=ft.Colors.GREY,
                        tooltip=f.source_evidence,
                    )
                )

            fact_card = ft.Card(
                content=ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(f"👤 {char_name}", weight=ft.FontWeight.BOLD, size=14),
                                    ft.Text(f"📍 {loc_name}", size=14),
                                    time_badge,
                                    source_badge,
                                    *evidence_controls,
                                ],
                                spacing=10,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE,
                                icon_color=ft.Colors.RED,
                                on_click=make_fact_delete_handler(f),
                                tooltip="删除",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=12,
                ),
            )
            fact_controls.append(fact_card)

    return ft.ExpansionPanel(
        header=ft.ListTile(title=ft.Text("✅ 手动添加事实")),
        content=ft.Container(
            content=ft.Column(
                controls=[*form_controls, *fact_controls],
                spacing=8,
            ),
            padding=ft.Padding.only(left=15, right=15, bottom=15),
        ),
    )
