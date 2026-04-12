"""推理矩阵页面 — Matrix tab.

Displays a time × character matrix table showing where each character was at each time slot.
Supports quick-add facts from cells, AI deduction triggers, and cascade elimination.
"""

from nicegui import ui

from src.models.puzzle import (
    Deduction,
    DeductionStatus,
    Project,
    SourceType,
)
from src.ui.state import app_state

# Module-level transient storage for contradictions (reset on each AI deduction)
_last_contradictions: list[dict] = []


def build_matrix_data(project: Project) -> list[dict]:
    """Build the matrix table data from a project.

    Each row represents a character. Columns are: character name + one per time slot.
    For each cell, stores the display value and a status suffix for color coding.

    This is a standalone testable function (not tied to UI).

    Returns:
        List of row dicts with keys:
        - 'id': character id
        - 'character': character name
        - '{time_slot}': display string for that cell
        - '{time_slot}_status': 'confirmed' | 'pending' | 'unknown'
    """
    rows = []
    for char in project.characters:
        row: dict = {"id": char.id, "character": char.name}
        for ts in project.time_slots:
            # Check for confirmed fact
            fact = next(
                (
                    f
                    for f in project.facts
                    if f.character_id == char.id and f.time_slot == ts
                ),
                None,
            )
            # Check for pending deduction
            deduction = next(
                (
                    d
                    for d in project.deductions
                    if d.character_id == char.id
                    and d.time_slot == ts
                    and d.status == DeductionStatus.pending
                ),
                None,
            )

            if fact:
                loc = next(
                    (l for l in project.locations if l.id == fact.location_id), None
                )
                row[ts] = loc.name if loc else "?"
                row[f"{ts}_status"] = "confirmed"
            elif deduction:
                loc = next(
                    (l for l in project.locations if l.id == deduction.location_id),
                    None,
                )
                row[ts] = f"({loc.name})" if loc else "(?)"
                row[f"{ts}_status"] = "pending"
            else:
                row[ts] = ""
                row[f"{ts}_status"] = "unknown"
        rows.append(row)
    return rows


def matrix_tab_content():
    """Render the reasoning matrix tab content."""
    global _last_contradictions

    with ui.column().classes("w-full q-pa-md gap-4"):
        ui.label("推理矩阵").classes("text-h5")

        if not app_state.current_project:
            ui.label("请先选择或创建一个项目").classes("text-body1 text-grey")
            return

        proj = app_state.current_project

        if not proj.characters or not proj.time_slots:
            with ui.card().classes("w-full q-pa-lg text-center"):
                ui.icon("grid_on", size="3em", color="grey")
                ui.label("请先在「管理」页面添加人物和时间段").classes(
                    "text-body1 text-grey q-mt-sm"
                )
                ui.label("矩阵需要至少一个人物和一个时间段才能显示").classes(
                    "text-caption text-grey"
                )
            return

        # --- Action buttons ---
        with ui.row().classes("gap-2 items-center"):

            async def run_ai_deduction():
                """Trigger a full AI deduction pass."""
                global _last_contradictions
                spinner = ui.spinner("dots", size="lg", color="primary")
                try:
                    from src.services.deduction import DeductionService

                    service = DeductionService()
                    ui.notify("🤖 正在进行 AI 推断...", type="info")
                    result = await service.run_deduction(proj)
                    deductions_data = result.get("deductions", [])
                    count = 0
                    for d_data in deductions_data:
                        ded = Deduction(
                            character_id=d_data.get("character_id", ""),
                            location_id=d_data.get("location_id", ""),
                            time_slot=d_data.get("time_slot", "00:00"),
                            confidence=d_data.get("confidence", "medium"),
                            reasoning=d_data.get("reasoning", ""),
                            supporting_script_ids=d_data.get(
                                "supporting_script_ids", []
                            ),
                            depends_on_fact_ids=d_data.get(
                                "depends_on_fact_ids", []
                            ),
                        )
                        app_state.add_deduction(ded)
                        count += 1

                    notes = result.get("notes", "")
                    contradictions = result.get("contradictions_detected", [])
                    new_chars = result.get("new_characters_detected", [])
                    new_locs = result.get("new_locations_detected", [])

                    # Store contradictions for display
                    _last_contradictions = contradictions or []

                    msg_parts = [f"AI 推断完成：新增 {count} 条推断"]
                    if contradictions:
                        msg_parts.append(f"⚠️ 发现 {len(contradictions)} 个矛盾")
                    if new_chars:
                        msg_parts.append(f"🆕 发现 {len(new_chars)} 个新人物")
                    if new_locs:
                        msg_parts.append(f"🆕 发现 {len(new_locs)} 个新地点")
                    ui.notify("；".join(msg_parts), type="positive")

                    # Show new entity discovery dialog
                    if new_chars or new_locs:
                        _show_new_entities_dialog(proj, new_chars, new_locs)

                    matrix_content.refresh()
                except ValueError as e:
                    ui.notify(str(e), type="negative")
                except Exception as e:
                    ui.notify(f"AI 推断失败: {str(e)[:200]}", type="negative", timeout=10000)
                finally:
                    spinner.delete()

            def run_cascade_deduction():
                """Trigger local elimination-based cascade."""
                try:
                    from src.services.deduction import DeductionService

                    new_deds = DeductionService.run_cascade(proj)
                    count = 0
                    for ded in new_deds:
                        # Avoid duplicating existing pending deductions
                        already_exists = any(
                            d.character_id == ded.character_id
                            and d.location_id == ded.location_id
                            and d.time_slot == ded.time_slot
                            and d.status == DeductionStatus.pending
                            for d in proj.deductions
                        )
                        if not already_exists:
                            app_state.add_deduction(ded)
                            count += 1
                    if count > 0:
                        ui.notify(
                            f"消元推断完成：新增 {count} 条确定推断",
                            type="positive",
                        )
                    else:
                        ui.notify("消元推断未发现新的确定推断", type="info")
                    matrix_content.refresh()
                except Exception as e:
                    ui.notify(f"消元推断失败: {str(e)[:200]}", type="negative")

            ui.button(
                "🤖 AI 推断", on_click=run_ai_deduction
            ).props("color=primary")
            ui.button(
                "🔄 消元推断", on_click=run_cascade_deduction
            ).props("color=secondary")

        # --- Matrix content (refreshable) ---
        @ui.refreshable
        def matrix_content():
            # Show contradictions card if any
            if _last_contradictions:
                _render_contradictions(_last_contradictions)
            _render_matrix(proj)

        matrix_content()


def _render_contradictions(contradictions: list[dict]):
    """Render a prominent contradiction warning card."""
    with ui.card().classes("w-full q-mb-md").style(
        "border: 2px solid #ff5252; background-color: rgba(255, 82, 82, 0.08);"
    ):
        with ui.card_section():
            with ui.row().classes("items-center gap-2"):
                ui.label("⚠️").classes("text-h5")
                ui.label("检测到矛盾").classes("text-h6 text-negative")
                ui.badge(
                    f"{len(contradictions)} 个", color="negative"
                ).classes("text-body2")

        with ui.card_section():
            for i, c in enumerate(contradictions, 1):
                desc = c.get("description", "未知矛盾")
                with ui.row().classes("items-start gap-2 q-mb-sm"):
                    ui.label(f"{i}.").classes("text-weight-bold text-negative")
                    with ui.column().classes("gap-0"):
                        ui.label(desc).classes("text-body1")
                        refs = []
                        involved_facts = c.get("involved_fact_ids", [])
                        involved_scripts = c.get("involved_script_ids", [])
                        if involved_facts:
                            refs.append(f"涉及 {len(involved_facts)} 条事实")
                        if involved_scripts:
                            refs.append(f"涉及 {len(involved_scripts)} 个剧本")
                        if refs:
                            ui.label("、".join(refs)).classes("text-caption text-grey")


def _show_new_entities_dialog(
    proj: Project,
    new_chars: list[dict],
    new_locs: list[dict],
):
    """Show a dialog listing newly discovered entities with add buttons."""
    with ui.dialog() as dlg, ui.card().classes("w-[500px]"):
        ui.label("🆕 发现新实体").classes("text-h6 q-mb-md")
        ui.label("AI 在分析中发现了以下未知人物/地点：").classes("text-body2 text-grey q-mb-md")

        if new_chars:
            ui.label("新人物").classes("text-subtitle1 text-weight-bold q-mb-sm")
            for ch in new_chars:
                name = ch.get("name", "未知")
                context = ch.get("context", "")
                with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"👤 {name}").classes("text-subtitle1 text-weight-bold")
                            if context:
                                ui.label(context).classes("text-caption text-grey")

                        def make_add_char_handler(ch_name):
                            def handler():
                                app_state.add_character(name=ch_name)
                                ui.notify(f"已添加人物「{ch_name}」", type="positive")
                            return handler

                        ui.button(
                            "添加", on_click=make_add_char_handler(name), icon="person_add"
                        ).props("dense color=primary outline")

        if new_locs:
            ui.label("新地点").classes("text-subtitle1 text-weight-bold q-mt-md q-mb-sm")
            for lo in new_locs:
                name = lo.get("name", "未知")
                context = lo.get("context", "")
                with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"📍 {name}").classes("text-subtitle1 text-weight-bold")
                            if context:
                                ui.label(context).classes("text-caption text-grey")

                        def make_add_loc_handler(lo_name):
                            def handler():
                                app_state.add_location(name=lo_name)
                                ui.notify(f"已添加地点「{lo_name}」", type="positive")
                            return handler

                        ui.button(
                            "添加", on_click=make_add_loc_handler(name), icon="add_location"
                        ).props("dense color=primary outline")

        with ui.row().classes("w-full justify-end q-mt-md"):
            ui.button("关闭", on_click=dlg.close).props("flat")

    dlg.open()


def _render_matrix(proj: Project):
    """Render the matrix table and statistics."""
    rows = build_matrix_data(proj)

    if not rows:
        ui.label("暂无数据").classes("text-body1 text-grey")
        return

    # Build columns definition
    columns = [
        {
            "name": "character",
            "label": "人物",
            "field": "character",
            "align": "left",
            "sortable": True,
            "headerStyle": "font-weight: bold",
        }
    ]
    for ts in proj.time_slots:
        columns.append(
            {
                "name": ts,
                "label": ts,
                "field": ts,
                "align": "center",
            }
        )

    table = ui.table(
        columns=columns,
        rows=rows,
        row_key="id",
    ).classes("w-full")

    # Add custom slot rendering for color-coded cells
    for ts in proj.time_slots:
        slot_name = f"body-cell-{ts}"
        table.add_slot(
            slot_name,
            f'''
            <q-td :props="props">
                <q-badge
                    v-if="props.row['{ts}_status'] === 'confirmed'"
                    color="green"
                    text-color="white"
                    class="text-body2 q-pa-sm cursor-pointer"
                >
                    {{{{ props.row['{ts}'] }}}}
                </q-badge>
                <q-badge
                    v-else-if="props.row['{ts}_status'] === 'pending'"
                    color="amber"
                    text-color="black"
                    class="text-body2 q-pa-sm cursor-pointer"
                >
                    {{{{ props.row['{ts}'] }}}}
                </q-badge>
                <span
                    v-else
                    class="text-grey cursor-pointer"
                    @click="$parent.$emit(\'cell-click\', {{{{ JSON.stringify({{char_id: props.row.id, time_slot: \'{ts}\'}}) }}}})"
                >
                    —
                </span>
            </q-td>
            ''',
        )

    # Handle cell click for quick-add
    table.on(
        "cell-click",
        lambda e: _show_quick_add_dialog(
            proj,
            e.args.get("char_id", "") if isinstance(e.args, dict) else "",
            e.args.get("time_slot", "") if isinstance(e.args, dict) else "",
        ),
    )

    # --- Statistics Summary ---
    ui.separator().classes("q-my-md")
    _render_statistics(proj)


def _show_quick_add_dialog(proj: Project, char_id: str, time_slot: str):
    """Show a dialog to quickly add a fact from a matrix cell click."""
    if not char_id or not time_slot:
        return

    char = next((c for c in proj.characters if c.id == char_id), None)
    if not char:
        return

    with ui.dialog() as dlg, ui.card().classes("w-96"):
        ui.label("快速添加事实").classes("text-h6 q-mb-md")
        ui.label(f"人物: {char.name}").classes("text-body1")
        ui.label(f"时间: {time_slot}").classes("text-body1")

        loc_options = {loc.id: loc.name for loc in proj.locations}
        loc_select = ui.select(
            options=loc_options,
            label="地点 *",
        ).classes("w-full")

        evidence_input = ui.input(
            label="证据/备注（可选）",
            placeholder="来源说明",
        ).classes("w-full")

        def do_add():
            if not loc_select.value:
                ui.notify("请选择地点", type="warning")
                return
            app_state.add_fact(
                character_id=char_id,
                location_id=loc_select.value,
                time_slot=time_slot,
                source_type=SourceType.user_input,
                source_evidence=evidence_input.value.strip() or None,
            )
            ui.notify("事实已添加", type="positive")
            dlg.close()

        with ui.row().classes("w-full justify-end q-mt-md"):
            ui.button("取消", on_click=dlg.close).props("flat")
            ui.button("确认", on_click=do_add).props("color=primary")

    dlg.open()


def _render_statistics(proj: Project):
    """Render matrix fill statistics below the table."""
    total_cells = len(proj.characters) * len(proj.time_slots)
    if total_cells == 0:
        return

    confirmed = 0
    pending = 0
    for char in proj.characters:
        for ts in proj.time_slots:
            has_fact = any(
                f.character_id == char.id and f.time_slot == ts for f in proj.facts
            )
            has_pending = any(
                d.character_id == char.id
                and d.time_slot == ts
                and d.status == DeductionStatus.pending
                for d in proj.deductions
            )
            if has_fact:
                confirmed += 1
            elif has_pending:
                pending += 1

    unknown = total_cells - confirmed - pending
    progress = confirmed / total_cells * 100 if total_cells > 0 else 0

    with ui.card().classes("w-full q-pa-md"):
        ui.label("📊 统计").classes("text-subtitle1 text-weight-bold q-mb-sm")
        with ui.row().classes("gap-6 flex-wrap"):
            with ui.column().classes("items-center"):
                ui.label(str(total_cells)).classes("text-h5")
                ui.label("总计格数").classes("text-caption text-grey")
            with ui.column().classes("items-center"):
                ui.label(str(confirmed)).classes("text-h5 text-positive")
                ui.label("已确认").classes("text-caption text-grey")
            with ui.column().classes("items-center"):
                ui.label(str(pending)).classes("text-h5 text-warning")
                ui.label("待审查").classes("text-caption text-grey")
            with ui.column().classes("items-center"):
                ui.label(str(unknown)).classes("text-h5 text-grey")
                ui.label("未知").classes("text-caption text-grey")
            with ui.column().classes("items-center"):
                ui.label(f"{progress:.0f}%").classes("text-h5 text-primary")
                ui.label("完成度").classes("text-caption text-grey")

        ui.linear_progress(value=progress / 100).classes("q-mt-sm").props(
            "color=primary"
        )
