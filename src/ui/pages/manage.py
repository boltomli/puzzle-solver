"""实体管理页面 — Manage tab.

Sections: 时间管理, 人物管理, 地点管理, 游戏规则, 手动添加事实.
"""

import re

from nicegui import ui

from src.models.puzzle import CharacterStatus, HintType, SourceType
from src.ui.state import app_state


def manage_tab_content():
    """Render the entity management tab content."""
    with ui.column().classes("w-full q-pa-md gap-4"):
        ui.label("管理").classes("text-h5")

        if not app_state.current_project:
            ui.label("请先选择或创建一个项目").classes("text-body1 text-grey")
            return

        # Show quick-start guidance if project is empty
        proj = app_state.current_project
        if not proj.characters and not proj.locations and not proj.time_slots:
            with ui.card().classes("w-full q-pa-md").style(
                "border: 1px dashed #64b5f6; background-color: rgba(100, 181, 246, 0.05);"
            ):
                ui.label("🚀 快速开始").classes("text-h6 q-mb-sm")
                ui.label("按以下顺序设置您的推理项目：").classes("text-body1 q-mb-sm")
                with ui.column().classes("gap-1"):
                    ui.label("1️⃣ 添加时间段 — 剧本中涉及的时间点（如 14:00, 15:00）").classes("text-body2")
                    ui.label("2️⃣ 添加人物 — 游戏中出现的角色").classes("text-body2")
                    ui.label("3️⃣ 添加地点 — 故事发生的地点").classes("text-body2")
                    ui.label("4️⃣ 录入规则 — 游戏的特殊规则和约束").classes("text-body2")
                    ui.label("5️⃣ 添加事实 — 您已确认的人物-地点-时间关系").classes("text-body2")

        # --- 4a: Time Slots ---
        _time_slots_section()

        # --- 4b: Characters ---
        _characters_section()

        # --- 4c: Locations ---
        _locations_section()

        # --- 4d: Hints / Rules ---
        _hints_section()

        # --- 4e: Manual Facts ---
        _facts_section()


# =============================================================================
# 4a. 时间管理
# =============================================================================

def _time_slots_section():
    """Time slot management section."""
    with ui.expansion("🕐 时间管理", icon="schedule").classes("w-full").props(
        "default-opened"
    ):
        @ui.refreshable
        def time_slot_list():
            if not app_state.current_project:
                return

            slots = app_state.current_project.time_slots
            if not slots:
                ui.label("暂无时间段，请添加").classes("text-body2 text-grey q-mb-sm")
            else:
                with ui.row().classes("gap-2 flex-wrap q-mb-md"):
                    for ts in sorted(slots):
                        with ui.badge(ts, color="primary").classes(
                            "text-body2 q-pa-sm"
                        ):
                            pass
                        ui.button(
                            icon="close",
                            on_click=lambda t=ts: _remove_time_slot(t),
                        ).props("flat dense round size=xs color=negative").classes(
                            "q-ml-n-sm"
                        )

        def _remove_time_slot(ts: str):
            app_state.remove_time_slot(ts)
            ui.notify(f"已删除时间段 {ts}", type="positive")
            time_slot_list.refresh()

        time_slot_list()

        # Add new time slot
        with ui.row().classes("items-end gap-2"):
            new_ts_input = ui.input(
                label="新增时间段",
                placeholder="HH:MM，例如 14:00",
            ).classes("w-40")

            def add_time_slot():
                val = new_ts_input.value.strip()
                if not val:
                    ui.notify("请输入时间", type="warning")
                    return
                if not re.match(r"^\d{2}:\d{2}$", val):
                    ui.notify("格式错误，请使用 HH:MM 格式", type="negative")
                    return
                added = app_state.add_time_slot(val)
                if added:
                    ui.notify(f"已添加时间段 {val}", type="positive")
                    new_ts_input.value = ""
                    time_slot_list.refresh()
                else:
                    ui.notify(f"时间段 {val} 已存在", type="warning")

            ui.button("添加", on_click=add_time_slot, icon="add").props(
                "color=primary dense"
            )


# =============================================================================
# 4b. 人物管理
# =============================================================================

def _characters_section():
    """Character management section."""
    with ui.expansion("👤 人物管理", icon="people").classes("w-full"):

        @ui.refreshable
        def character_list():
            if not app_state.current_project:
                return

            chars = app_state.current_project.characters
            if not chars:
                ui.label("暂无人物，请添加").classes("text-body2 text-grey q-mb-sm")
                return

            # Table display
            columns = [
                {"name": "name", "label": "姓名", "field": "name", "align": "left"},
                {"name": "aliases", "label": "别名", "field": "aliases", "align": "left"},
                {"name": "status", "label": "状态", "field": "status", "align": "center"},
                {"name": "description", "label": "描述", "field": "description", "align": "left"},
                {"name": "actions", "label": "操作", "field": "actions", "align": "center"},
            ]
            rows = []
            for c in chars:
                rows.append({
                    "id": c.id,
                    "name": c.name,
                    "aliases": ", ".join(c.aliases) if c.aliases else "-",
                    "status": _status_label(c.status),
                    "description": c.description or "-",
                })

            for c in chars:
                with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            with ui.row().classes("items-center gap-2"):
                                ui.label(c.name).classes("text-subtitle1 text-weight-bold")
                                ui.badge(
                                    _status_label(c.status),
                                    color=_status_color(c.status),
                                ).classes("text-caption")
                            if c.aliases:
                                ui.label(f"别名: {', '.join(c.aliases)}").classes(
                                    "text-caption text-grey"
                                )
                            if c.description:
                                ui.label(c.description).classes("text-body2 text-grey")

                        with ui.row().classes("gap-1"):
                            ui.button(
                                icon="edit",
                                on_click=lambda cid=c.id: _edit_character_dialog(cid),
                            ).props("flat dense round")
                            ui.button(
                                icon="delete",
                                on_click=lambda cid=c.id, cname=c.name: _confirm_delete_character(cid, cname),
                            ).props("flat dense round color=negative")

        def _confirm_delete_character(char_id: str, char_name: str):
            with ui.dialog() as dlg, ui.card():
                ui.label(f"确认删除人物「{char_name}」？").classes("text-h6")
                ui.label("此操作不可撤销").classes("text-body2 text-grey")
                with ui.row().classes("w-full justify-end q-mt-md"):
                    ui.button("取消", on_click=dlg.close).props("flat")

                    def do_del():
                        app_state.remove_character(char_id)
                        ui.notify("删除成功", type="positive")
                        dlg.close()
                        character_list.refresh()

                    ui.button("删除", on_click=do_del).props("color=negative")
            dlg.open()

        def _edit_character_dialog(char_id: str):
            char = next(
                (c for c in app_state.current_project.characters if c.id == char_id),
                None,
            )
            if not char:
                return
            _show_character_dialog(
                title="编辑人物",
                initial_name=char.name,
                initial_aliases=", ".join(char.aliases),
                initial_desc=char.description or "",
                initial_status=char.status.value,
                on_save=lambda n, a, d, s: _do_update_character(char_id, n, a, d, s),
            )

        def _do_update_character(char_id, name, aliases_str, desc, status_val):
            aliases = [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
            app_state.update_character(
                char_id,
                name=name,
                aliases=aliases,
                description=desc or None,
                status=CharacterStatus(status_val),
            )
            ui.notify("人物已更新", type="positive")
            character_list.refresh()

        character_list()

        # Add character button
        def _add_character():
            _show_character_dialog(
                title="添加人物",
                on_save=lambda n, a, d, s: _do_add_character(n, a, d, s),
            )

        def _do_add_character(name, aliases_str, desc, status_val):
            aliases = [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
            app_state.add_character(
                name=name,
                aliases=aliases,
                description=desc or None,
                status=CharacterStatus(status_val),
            )
            ui.notify("人物已添加", type="positive")
            character_list.refresh()

        ui.button("添加人物", on_click=_add_character, icon="person_add").props(
            "color=primary"
        )


def _show_character_dialog(
    title: str = "人物",
    initial_name: str = "",
    initial_aliases: str = "",
    initial_desc: str = "",
    initial_status: str = "confirmed",
    on_save=None,
):
    """Reusable dialog for adding/editing a character."""
    with ui.dialog() as dlg, ui.card().classes("w-96"):
        ui.label(title).classes("text-h6 q-mb-md")

        name_input = ui.input(label="姓名 *", value=initial_name).classes("w-full")
        aliases_input = ui.input(
            label="别名（逗号分隔）",
            value=initial_aliases,
            placeholder="张三, 小张",
        ).classes("w-full")
        desc_input = ui.input(
            label="描述（可选）",
            value=initial_desc,
        ).classes("w-full")
        status_options = {
            "confirmed": "已确认",
            "suspected": "疑似",
            "unknown": "未知",
        }
        status_select = ui.select(
            options=status_options,
            value=initial_status,
            label="状态",
        ).classes("w-full")

        error_label = ui.label("").classes("text-negative")

        def save():
            name = name_input.value.strip()
            if not name:
                error_label.text = "姓名不能为空"
                return
            if on_save:
                on_save(name, aliases_input.value, desc_input.value.strip(), status_select.value)
            dlg.close()

        with ui.row().classes("w-full justify-end q-mt-md"):
            ui.button("取消", on_click=dlg.close).props("flat")
            ui.button("保存", on_click=save).props("color=primary")

    dlg.open()


def _status_label(status: CharacterStatus) -> str:
    return {"confirmed": "已确认", "suspected": "疑似", "unknown": "未知"}.get(
        status.value, status.value
    )


def _status_color(status: CharacterStatus) -> str:
    return {"confirmed": "positive", "suspected": "warning", "unknown": "grey"}.get(
        status.value, "grey"
    )


# =============================================================================
# 4c. 地点管理
# =============================================================================

def _locations_section():
    """Location management section."""
    with ui.expansion("📍 地点管理", icon="place").classes("w-full"):

        @ui.refreshable
        def location_list():
            if not app_state.current_project:
                return

            locs = app_state.current_project.locations
            if not locs:
                ui.label("暂无地点，请添加").classes("text-body2 text-grey q-mb-sm")
                return

            for loc in locs:
                with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(loc.name).classes("text-subtitle1 text-weight-bold")
                            if loc.aliases:
                                ui.label(f"别名: {', '.join(loc.aliases)}").classes(
                                    "text-caption text-grey"
                                )
                            if loc.description:
                                ui.label(loc.description).classes("text-body2 text-grey")

                        with ui.row().classes("gap-1"):
                            ui.button(
                                icon="edit",
                                on_click=lambda lid=loc.id: _edit_location_dialog(lid),
                            ).props("flat dense round")
                            ui.button(
                                icon="delete",
                                on_click=lambda lid=loc.id, lname=loc.name: _confirm_delete_location(lid, lname),
                            ).props("flat dense round color=negative")

        def _confirm_delete_location(loc_id: str, loc_name: str):
            with ui.dialog() as dlg, ui.card():
                ui.label(f"确认删除地点「{loc_name}」？").classes("text-h6")
                ui.label("此操作不可撤销").classes("text-body2 text-grey")
                with ui.row().classes("w-full justify-end q-mt-md"):
                    ui.button("取消", on_click=dlg.close).props("flat")

                    def do_del():
                        app_state.remove_location(loc_id)
                        ui.notify("删除成功", type="positive")
                        dlg.close()
                        location_list.refresh()

                    ui.button("删除", on_click=do_del).props("color=negative")
            dlg.open()

        def _edit_location_dialog(loc_id: str):
            loc = next(
                (l for l in app_state.current_project.locations if l.id == loc_id),
                None,
            )
            if not loc:
                return
            _show_location_dialog(
                title="编辑地点",
                initial_name=loc.name,
                initial_aliases=", ".join(loc.aliases),
                initial_desc=loc.description or "",
                on_save=lambda n, a, d: _do_update_location(loc_id, n, a, d),
            )

        def _do_update_location(loc_id, name, aliases_str, desc):
            aliases = [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
            app_state.update_location(
                loc_id,
                name=name,
                aliases=aliases,
                description=desc or None,
            )
            ui.notify("地点已更新", type="positive")
            location_list.refresh()

        location_list()

        # Add location button
        def _add_location():
            _show_location_dialog(
                title="添加地点",
                on_save=lambda n, a, d: _do_add_location(n, a, d),
            )

        def _do_add_location(name, aliases_str, desc):
            aliases = [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
            app_state.add_location(
                name=name,
                aliases=aliases,
                description=desc or None,
            )
            ui.notify("地点已添加", type="positive")
            location_list.refresh()

        ui.button("添加地点", on_click=_add_location, icon="add_location").props(
            "color=primary"
        )


def _show_location_dialog(
    title: str = "地点",
    initial_name: str = "",
    initial_aliases: str = "",
    initial_desc: str = "",
    on_save=None,
):
    """Reusable dialog for adding/editing a location."""
    with ui.dialog() as dlg, ui.card().classes("w-96"):
        ui.label(title).classes("text-h6 q-mb-md")

        name_input = ui.input(label="名称 *", value=initial_name).classes("w-full")
        aliases_input = ui.input(
            label="别名（逗号分隔）",
            value=initial_aliases,
            placeholder="图书馆, Library",
        ).classes("w-full")
        desc_input = ui.input(
            label="描述（可选）",
            value=initial_desc,
        ).classes("w-full")

        error_label = ui.label("").classes("text-negative")

        def save():
            name = name_input.value.strip()
            if not name:
                error_label.text = "名称不能为空"
                return
            if on_save:
                on_save(name, aliases_input.value, desc_input.value.strip())
            dlg.close()

        with ui.row().classes("w-full justify-end q-mt-md"):
            ui.button("取消", on_click=dlg.close).props("flat")
            ui.button("保存", on_click=save).props("color=primary")

    dlg.open()


# =============================================================================
# 4d. 游戏规则
# =============================================================================

def _hints_section():
    """Hints/rules/constraints management section."""
    with ui.expansion("📋 游戏规则", icon="rule").classes("w-full"):

        @ui.refreshable
        def hint_list():
            if not app_state.current_project:
                return

            hints = app_state.current_project.hints
            if not hints:
                ui.label("暂无规则或提示，请添加").classes("text-body2 text-grey q-mb-sm")
                return

            for h in hints:
                with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-2"):
                            ui.badge(
                                _hint_type_label(h.type),
                                color=_hint_type_color(h.type),
                            )
                            ui.label(h.content).classes("text-body1")
                        ui.button(
                            icon="delete",
                            on_click=lambda hid=h.id: _delete_hint(hid),
                        ).props("flat dense round color=negative")

        def _delete_hint(hint_id: str):
            app_state.remove_hint(hint_id)
            ui.notify("删除成功", type="positive")
            hint_list.refresh()

        hint_list()

        # Add hint
        def _add_hint():
            with ui.dialog() as dlg, ui.card().classes("w-96"):
                ui.label("添加规则").classes("text-h6 q-mb-md")

                type_options = {
                    "rule": "规则 (Rule)",
                    "hint": "提示 (Hint)",
                    "constraint": "约束 (Constraint)",
                }
                type_select = ui.select(
                    options=type_options,
                    value="rule",
                    label="类型",
                ).classes("w-full")

                content_input = ui.textarea(
                    label="内容 *",
                    placeholder="例如：每个人每个时间段只能在一个地点",
                ).classes("w-full").props("rows=3")

                error_label = ui.label("").classes("text-negative")

                def save():
                    content = content_input.value.strip()
                    if not content:
                        error_label.text = "内容不能为空"
                        return
                    app_state.add_hint(
                        hint_type=HintType(type_select.value),
                        content=content,
                    )
                    ui.notify("规则已添加", type="positive")
                    dlg.close()
                    hint_list.refresh()

                with ui.row().classes("w-full justify-end q-mt-md"):
                    ui.button("取消", on_click=dlg.close).props("flat")
                    ui.button("保存", on_click=save).props("color=primary")

            dlg.open()

        ui.button("添加规则", on_click=_add_hint, icon="add").props("color=primary")


def _hint_type_label(ht: HintType) -> str:
    return {"rule": "规则", "hint": "提示", "constraint": "约束"}.get(ht.value, ht.value)


def _hint_type_color(ht: HintType) -> str:
    return {"rule": "primary", "hint": "info", "constraint": "warning"}.get(
        ht.value, "grey"
    )


# =============================================================================
# 4e. 手动添加事实
# =============================================================================

def _facts_section():
    """Manual fact entry section."""
    with ui.expansion("✅ 手动添加事实", icon="fact_check").classes("w-full"):

        @ui.refreshable
        def facts_content():
            if not app_state.current_project:
                return

            proj = app_state.current_project
            chars = proj.characters
            locs = proj.locations
            slots = proj.time_slots

            if not chars or not locs or not slots:
                ui.label(
                    "请先添加人物、地点和时间段后再录入事实"
                ).classes("text-body2 text-grey q-mb-sm")
            else:
                # Form for adding facts
                char_options = {c.id: c.name for c in chars}
                loc_options = {l.id: l.name for l in locs}
                slot_options = {s: s for s in sorted(slots)}

                with ui.card().classes("w-full q-pa-md q-mb-md"):
                    with ui.row().classes("w-full items-end gap-4 flex-wrap"):
                        char_sel = ui.select(
                            options=char_options,
                            label="人物 *",
                        ).classes("min-w-[150px]")

                        loc_sel = ui.select(
                            options=loc_options,
                            label="地点 *",
                        ).classes("min-w-[150px]")

                        slot_sel = ui.select(
                            options=slot_options,
                            label="时间段 *",
                        ).classes("min-w-[120px]")

                        evidence_input = ui.input(
                            label="证据/备注",
                            placeholder="来源说明",
                        ).classes("flex-grow")

                    def add_fact():
                        if not char_sel.value:
                            ui.notify("请选择人物", type="warning")
                            return
                        if not loc_sel.value:
                            ui.notify("请选择地点", type="warning")
                            return
                        if not slot_sel.value:
                            ui.notify("请选择时间段", type="warning")
                            return
                        app_state.add_fact(
                            character_id=char_sel.value,
                            location_id=loc_sel.value,
                            time_slot=slot_sel.value,
                            source_type=SourceType.user_input,
                            source_evidence=evidence_input.value.strip() or None,
                        )
                        char_sel.value = None
                        loc_sel.value = None
                        slot_sel.value = None
                        evidence_input.value = ""
                        ui.notify("事实已添加", type="positive")
                        facts_content.refresh()

                    ui.button("添加事实", on_click=add_fact, icon="add").props(
                        "color=primary"
                    ).classes("q-mt-sm")

            # Show existing facts
            facts = proj.facts
            if not facts:
                ui.label("暂无事实记录").classes("text-body2 text-grey q-mt-md")
            else:
                ui.separator().classes("q-my-md")
                ui.label(f"已有 {len(facts)} 条事实").classes("text-subtitle2 q-mb-sm")

                # Build lookup maps for display
                char_map = {c.id: c.name for c in chars}
                loc_map = {l.id: l.name for l in locs}

                for f in facts:
                    char_name = char_map.get(f.character_id, f.character_id[:8])
                    loc_name = loc_map.get(f.location_id, f.location_id[:8])
                    source_label = _source_type_label(f.source_type)

                    with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                        with ui.row().classes("w-full items-center justify-between"):
                            with ui.row().classes("items-center gap-3"):
                                ui.label(f"👤 {char_name}").classes("text-weight-bold")
                                ui.label(f"📍 {loc_name}")
                                ui.badge(f.time_slot, color="primary")
                                ui.badge(source_label, color="grey")
                            with ui.row().classes("items-center gap-1"):
                                if f.source_evidence:
                                    ui.tooltip(f.source_evidence)
                                    ui.icon("info", size="sm", color="grey")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda fid=f.id: _delete_fact(fid),
                                ).props("flat dense round color=negative")

        def _delete_fact(fact_id: str):
            with ui.dialog() as dlg, ui.card():
                ui.label("确认删除此事实？").classes("text-h6")
                ui.label("此操作不可撤销").classes("text-body2 text-grey")
                with ui.row().classes("w-full justify-end q-mt-md"):
                    ui.button("取消", on_click=dlg.close).props("flat")

                    def do_del():
                        app_state.remove_fact(fact_id)
                        ui.notify("删除成功", type="positive")
                        dlg.close()
                        facts_content.refresh()

                    ui.button("删除", on_click=do_del).props("color=negative")
            dlg.open()

        facts_content()


def _source_type_label(st: SourceType) -> str:
    return {
        "script_explicit": "剧本明示",
        "user_input": "手动输入",
        "ai_deduction": "AI推断",
        "game_hint": "游戏提示",
    }.get(st.value, st.value)
