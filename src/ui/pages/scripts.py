"""剧本管理页面 — Scripts tab (Flet version).

Allows adding, viewing, and deleting scripts (scene text from the game).
Provides AI-powered script analysis with entity extraction and deduction creation.
"""

import re

import flet as ft
from loguru import logger

from src.models.puzzle import ConfidenceLevel, Deduction, DeductionStatus, EntityKind
from src.services.config import load_config
from src.ui.state import app_state

# ---------------------------------------------------------------------------
# Pure logic helpers — tested by tests/test_scripts.py
# ---------------------------------------------------------------------------


def _is_api_configured() -> bool:
    """Check if API is configured for AI features."""
    config = load_config()
    return bool(config.get("api_base_url") and config.get("model"))


def _create_single_deduction(proj, fact_dict: dict, script_id: str) -> bool:
    """Convert a single direct_fact from analysis into a pending Deduction.

    Maps character_name and location_name back to IDs from the project.
    Maps time_slot label back to a TimeSlot ID.
    Returns True if the deduction was successfully created.
    """
    char_name = fact_dict.get("character_name", "")
    loc_name = fact_dict.get("location_name", "")
    ts = fact_dict.get("time_slot", "")
    confidence_str = fact_dict.get("confidence", "medium")
    evidence = fact_dict.get("evidence", "")

    char = next((c for c in proj.characters if c.name.lower() == char_name.lower()), None)
    loc = next((lo for lo in proj.locations if lo.name.lower() == loc_name.lower()), None)

    if not char or not loc:
        logger.warning(
            "_create_single_deduction: cannot resolve char={!r}(found={}) loc={!r}(found={}) ts={!r}",
            char_name,
            char is not None,
            loc_name,
            loc is not None,
            ts,
        )
        return False

    # Build label → ID mapping for time slots
    ts_label_map: dict[str, str] = {}
    for ts_obj in proj.time_slots:
        key = f"{ts_obj.label}({ts_obj.description})" if ts_obj.description else ts_obj.label
        ts_label_map[key] = ts_obj.id
        # Also map bare label for backward compat
        if ts_obj.label not in ts_label_map:
            ts_label_map[ts_obj.label] = ts_obj.id

    ts_id = ts_label_map.get(ts)
    if not ts_id:
        logger.warning("_create_single_deduction: unknown time_slot label={!r}", ts)
        return False

    try:
        conf = ConfidenceLevel(confidence_str)
    except ValueError:
        conf = ConfidenceLevel.medium

    deduction = Deduction(
        character_id=char.id,
        location_id=loc.id,
        time_slot=ts_id,
        confidence=conf,
        reasoning=evidence or f"剧本分析：{char_name} 在 {ts} 位于 {loc_name}",
        supporting_script_ids=[script_id],
        status=DeductionStatus.pending,
    )
    added = app_state.add_deduction(deduction)
    if added:
        logger.info(
            "_create_single_deduction: created char={!r} loc={!r} ts={!r} conf={}",
            char_name,
            loc_name,
            ts,
            conf,
        )
    else:
        logger.debug(
            "_create_single_deduction: skipped duplicate char={!r} loc={!r} ts={!r}",
            char_name,
            loc_name,
            ts,
        )
    return added


def _create_deductions_from_facts(proj, direct_facts: list[dict], script_id: str) -> int:
    """Convert direct_facts from analysis into pending Deduction objects.

    Maps character_name and location_name back to IDs from the project.
    Maps time_slot labels back to TimeSlot IDs.
    Returns the number of deductions successfully created.
    """
    # Build label → ID mapping for time slots
    ts_label_map: dict[str, str] = {}
    for ts_obj in proj.time_slots:
        key = f"{ts_obj.label}({ts_obj.description})" if ts_obj.description else ts_obj.label
        ts_label_map[key] = ts_obj.id
        # Also map bare label for backward compat
        if ts_obj.label not in ts_label_map:
            ts_label_map[ts_obj.label] = ts_obj.id

    created = 0
    for df in direct_facts:
        char_name = df.get("character_name", "")
        loc_name = df.get("location_name", "")
        ts = df.get("time_slot", "")
        confidence_str = df.get("confidence", "medium")
        evidence = df.get("evidence", "")

        # Map names to IDs
        char = next((c for c in proj.characters if c.name.lower() == char_name.lower()), None)
        loc = next((lo for lo in proj.locations if lo.name.lower() == loc_name.lower()), None)

        # Skip if we can't resolve both character and location
        if not char or not loc:
            continue
        # Map time_slot label to ID
        ts_id = ts_label_map.get(ts)
        if not ts_id:
            continue

        # Map confidence string to enum
        try:
            conf = ConfidenceLevel(confidence_str)
        except ValueError:
            conf = ConfidenceLevel.medium

        deduction = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts_id,
            confidence=conf,
            reasoning=evidence or f"剧本分析：{char_name} 在 {ts} 位于 {loc_name}",
            supporting_script_ids=[script_id],
            status=DeductionStatus.pending,
        )
        if app_state.add_deduction(deduction):
            created += 1

    return created


# ---------------------------------------------------------------------------
# Flet UI builder
# ---------------------------------------------------------------------------


def build_scripts_tab(page: ft.Page) -> ft.Control:
    """Build and return the scripts management tab control tree.

    Contains:
    - Add script form (title, text, notes, save button)
    - Script list (newest first, expandable with full text and action buttons)
    - Analysis results dialog with entity add / deduction add buttons
    """
    outer_container = ft.Container(expand=True)

    def _show_snackbar(message: str, color: str | None = None):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=color,
        )
        page.snack_bar.open = True
        page.update()

    def refresh():
        """Rebuild the scripts tab content after state changes."""
        outer_container.content = _build_content(page, refresh, _show_snackbar)
        page.update()

    outer_container.content = _build_content(page, refresh, _show_snackbar)
    return ft.Column(
        controls=[
            ft.Text("剧本管理", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            outer_container,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        expand=True,
    )


def _build_content(page: ft.Page, refresh, show_snackbar) -> ft.Control:
    """Build the full scripts page content."""
    if not app_state.current_project:
        return ft.Text("请先选择或创建一个项目", color=ft.Colors.GREY, size=16)

    proj = app_state.current_project
    controls: list[ft.Control] = []

    # --- API not configured banner ---
    if not _is_api_configured():
        controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.AMBER),
                        ft.Text(
                            "API 未配置，AI 功能（自动分析、推断）暂不可用。请前往「设置」页面配置 API。",
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

    # --- Unanalyzed scripts banner ---
    unanalyzed = [s for s in proj.scripts if s.analysis_result is None]
    if unanalyzed and _is_api_configured():
        unanalyzed_names = [
            s.title or f"剧本 #{s.metadata.source_order or '?'}" for s in unanalyzed
        ]

        async def auto_analyze_all(e):
            analyze_btn.disabled = True
            analyze_btn.text = "正在分析..."
            page.update()
            for s in unanalyzed:
                await _run_script_analysis(page, s.id, refresh, show_snackbar)
            refresh()

        analyze_btn = ft.ElevatedButton(
            f"🤖 自动分析 {len(unanalyzed)} 个剧本",
            on_click=auto_analyze_all,
        )

        controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.BLUE),
                        ft.Column(
                            [
                                ft.Text(
                                    f"有 {len(unanalyzed)} 个剧本尚未分析：{', '.join(unanalyzed_names)}",
                                    size=14,
                                ),
                                analyze_btn,
                            ],
                            spacing=6,
                            expand=True,
                        ),
                    ],
                    spacing=10,
                ),
                border=ft.Border.all(1, ft.Colors.BLUE_200),
                border_radius=8,
                padding=12,
                margin=ft.Margin.only(bottom=10),
            )
        )

    # --- Add Script Form ---
    title_field = ft.TextField(
        label="标题（可选）",
        hint_text="例如：第一幕、Alice的剧本",
    )
    raw_text_field = ft.TextField(
        label="剧本文本 *",
        hint_text="在此粘贴剧本文本...",
        multiline=True,
        min_lines=6,
    )
    notes_field = ft.TextField(
        label="备注（可选）",
        hint_text="你的备注或观察",
    )

    async def save_script(e):
        text = (raw_text_field.value or "").strip()
        if not text:
            show_snackbar("请输入剧本文本", ft.Colors.AMBER)
            return

        script = app_state.add_script(
            raw_text=text,
            title=(title_field.value or "").strip() or None,
            user_notes=(notes_field.value or "").strip() or None,
        )

        # Clear inputs
        title_field.value = ""
        raw_text_field.value = ""
        notes_field.value = ""
        show_snackbar("剧本已保存", ft.Colors.GREEN)
        refresh()

        # Auto-trigger script analysis
        if _is_api_configured():
            await _run_script_analysis(page, script.id, refresh, show_snackbar)
        else:
            show_snackbar(
                "剧本已保存。配置 API 后可自动分析剧本。",
                ft.Colors.BLUE,
            )

    controls.append(
        ft.Card(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("添加新剧本", size=20, weight=ft.FontWeight.BOLD),
                        title_field,
                        raw_text_field,
                        notes_field,
                        ft.Row(
                            controls=[
                                ft.ElevatedButton(
                                    "保存剧本",
                                    icon=ft.Icons.SAVE,
                                    on_click=save_script,
                                ),
                                ft.Text(
                                    "Ctrl+Enter 快捷保存",
                                    size=12,
                                    color=ft.Colors.GREY,
                                ),
                            ],
                            spacing=10,
                        ),
                    ],
                    spacing=12,
                ),
                padding=20,
            ),
        )
    )

    # --- Script List ---
    scripts = proj.scripts
    if not scripts:
        controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.DESCRIPTION, size=48, color=ft.Colors.GREY),
                        ft.Text("暂无剧本", size=16, color=ft.Colors.GREY),
                        ft.Text(
                            "请在上方添加剧本文本，AI 将帮助您提取人物、地点等信息",
                            size=13,
                            color=ft.Colors.GREY,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                padding=40,
            )
        )
    else:
        controls.append(ft.Text(f"已有 {len(scripts)} 个剧本", size=16, weight=ft.FontWeight.W_500))

        for script in reversed(scripts):  # Newest first
            header_text = _script_header(script)
            api_ok = _is_api_configured()

            # --- Build action buttons ---
            action_buttons: list[ft.Control] = []

            def make_analyze_handler(s_id):
                async def handler(e):
                    await _run_script_analysis(page, s_id, refresh, show_snackbar)

                return handler

            def make_view_results_handler(s_result, s_id):
                def handler(e):
                    _show_analysis_results_dialog(
                        page, proj, s_result, s_id, refresh, show_snackbar
                    )

                return handler

            def make_delete_handler(s_id, s_title):
                def handler(e):
                    _confirm_delete_script(page, s_id, s_title, refresh, show_snackbar)

                return handler

            if script.analysis_result is not None:
                action_buttons.append(
                    ft.ElevatedButton(
                        "📊 查看分析结果",
                        icon=ft.Icons.ASSESSMENT,
                        on_click=make_view_results_handler(script.analysis_result, script.id),
                        color=ft.Colors.GREEN,
                    )
                )
                reanalyze_btn = ft.OutlinedButton(
                    "🔄 重新分析",
                    icon=ft.Icons.REFRESH,
                    on_click=make_analyze_handler(script.id) if api_ok else None,
                    disabled=not api_ok,
                )
                if not api_ok:
                    reanalyze_btn.tooltip = "请先在设置页面配置 API"
                action_buttons.append(reanalyze_btn)
            else:
                analyze_btn = ft.OutlinedButton(
                    "🤖 分析此剧本",
                    icon=ft.Icons.PSYCHOLOGY,
                    on_click=make_analyze_handler(script.id) if api_ok else None,
                    disabled=not api_ok,
                )
                if not api_ok:
                    analyze_btn.tooltip = "请先在设置页面配置 API"
                action_buttons.append(analyze_btn)

            action_buttons.append(
                ft.TextButton(
                    "删除",
                    icon=ft.Icons.DELETE,
                    on_click=make_delete_handler(script.id, script.title or "无标题"),
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                )
            )

            # --- Build expanded content ---
            expanded_controls: list[ft.Control] = []
            if script.metadata.user_notes:
                expanded_controls.append(
                    ft.Text(
                        f"📝 备注: {script.metadata.user_notes}",
                        size=13,
                        color=ft.Colors.GREY,
                    )
                )
            if script.metadata.stated_time:
                expanded_controls.append(
                    ft.Text(f"🕐 时间: {script.metadata.stated_time}", size=13)
                )
            if script.metadata.stated_location:
                expanded_controls.append(
                    ft.Text(f"📍 地点: {script.metadata.stated_location}", size=13)
                )
            if expanded_controls:
                expanded_controls.append(ft.Divider())

            # Full text in monospace container
            expanded_controls.append(
                ft.Container(
                    content=ft.Text(
                        script.raw_text,
                        selectable=True,
                        font_family="Consolas, monospace",
                        size=13,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                    border_radius=4,
                    padding=12,
                )
            )

            # Action buttons row
            expanded_controls.append(
                ft.Row(
                    controls=action_buttons,
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            )

            controls.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.ExpansionTile(
                            title=ft.Text(header_text, size=14),
                            leading=ft.Icon(ft.Icons.DESCRIPTION),
                            controls=[
                                ft.Container(
                                    content=ft.Column(
                                        controls=expanded_controls,
                                        spacing=8,
                                    ),
                                    padding=ft.Padding.only(left=16, right=16, bottom=16),
                                )
                            ],
                        ),
                        padding=0,
                    ),
                )
            )

    return ft.Column(controls=controls, spacing=12)


# ---------------------------------------------------------------------------
# Analysis dialog
# ---------------------------------------------------------------------------


def _show_analysis_results_dialog(
    page: ft.Page,
    proj,
    result: dict,
    script_id: str,
    refresh,
    show_snackbar,
):
    """Show the script analysis results in an AlertDialog."""
    chars_mentioned = result.get("characters_mentioned", [])
    locs_mentioned = result.get("locations_mentioned", [])
    time_refs = result.get("time_references", [])
    direct_facts = result.get("direct_facts", [])

    new_chars = [
        ch
        for ch in chars_mentioned
        if ch.get("is_new", False)
        and not app_state.is_entity_ignored(EntityKind.character, ch.get("name", ""))
    ]
    new_locs = [
        lo
        for lo in locs_mentioned
        if lo.get("is_new", False)
        and not app_state.is_entity_ignored(EntityKind.location, lo.get("name", ""))
    ]
    existing_time_slots = {ts.label for ts in proj.time_slots} if proj else set()
    new_time_refs = [
        tr
        for tr in time_refs
        if tr.get("time_slot")
        and re.match(r"^\d{2}:\d{2}$", tr["time_slot"])
        and tr["time_slot"] not in existing_time_slots
        and not app_state.is_entity_ignored(EntityKind.time_slot, tr["time_slot"])
    ]

    content_controls: list[ft.Control] = []

    # --- "全部添加实体" button ---
    has_new_entities = new_chars or new_locs or new_time_refs
    if has_new_entities:
        add_all_entities_btn = ft.ElevatedButton(
            "全部添加实体",
            icon=ft.Icons.PLAYLIST_ADD,
            tooltip="仅添加新发现的人物、地点和时间段，不包含推断事实",
        )

        def add_all_entities(e):
            added_count = 0
            for ch in new_chars:
                ch_name = ch.get("name", "")
                if ch_name:
                    existing_names = {c.name for c in proj.characters}
                    if ch_name not in existing_names:
                        app_state.add_character(name=ch_name)
                        added_count += 1
            for lo in new_locs:
                lo_name = lo.get("name", "")
                if lo_name:
                    existing_names = {loc.name for loc in proj.locations}
                    if lo_name not in existing_names:
                        app_state.add_location(name=lo_name)
                        added_count += 1
            for tr in new_time_refs:
                ts = tr.get("time_slot", "")
                existing_labels = {t.label for t in proj.time_slots}
                if ts and ts not in existing_labels:
                    try:
                        app_state.add_time_slot(ts)
                        added_count += 1
                    except ValueError:
                        pass
            show_snackbar(f"已批量添加 {added_count} 个实体（人物/地点/时间段）", ft.Colors.GREEN)
            add_all_entities_btn.disabled = True
            add_all_entities_btn.text = "已添加"
            page.update()

        add_all_entities_btn.on_click = add_all_entities
        content_controls.append(add_all_entities_btn)

    # --- Characters ---
    if chars_mentioned:
        content_controls.append(
            ft.Text(
                f"👤 人物 ({len(chars_mentioned)})",
                size=16,
                weight=ft.FontWeight.BOLD,
            )
        )
        for ch in chars_mentioned:
            name = ch.get("name", "未知")
            is_new = ch.get("is_new", False)
            context = ch.get("context", "")
            row_controls: list[ft.Control] = [ft.Text(name, weight=ft.FontWeight.BOLD)]
            if is_new:
                row_controls.append(
                    ft.Container(
                        content=ft.Text("新发现", size=11, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.ORANGE,
                        border_radius=4,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    )
                )
            if context:
                row_controls.append(ft.Text(context, size=12, color=ft.Colors.GREY))

            right_controls: list[ft.Control] = []
            if is_new:
                action_row = ft.Row(spacing=4)

                def make_add_char(ch_name, row_ref):
                    def handler(e):
                        app_state.add_character(name=ch_name)
                        show_snackbar(f"已添加人物「{ch_name}」", ft.Colors.GREEN)
                        row_ref.controls = [ft.Text("已添加", color=ft.Colors.GREEN, size=13)]
                        page.update()

                    return handler

                def make_merge_char(ch_name, row_ref):
                    def handler(e):
                        chars = (
                            app_state.current_project.characters
                            if app_state.current_project
                            else []
                        )
                        if not chars:
                            show_snackbar("项目中暂无人物可合并", ft.Colors.AMBER)
                            return
                        dd = ft.Dropdown(
                            label="合并到",
                            options=[ft.dropdown.Option(key=c.id, text=c.name) for c in chars],
                            width=200,
                        )

                        def do_merge(e2):
                            if not dd.value:
                                show_snackbar("请选择目标人物", ft.Colors.AMBER)
                                return
                            app_state.merge_character(ch_name, dd.value)
                            target = next(
                                (
                                    c
                                    for c in app_state.current_project.characters
                                    if c.id == dd.value
                                ),
                                None,
                            )
                            show_snackbar(
                                f"已将「{ch_name}」合并为「{target.name if target else dd.value}」的别名",
                                ft.Colors.GREEN,
                            )
                            merge_dlg.open = False
                            row_ref.controls = [ft.Text("已合并", color=ft.Colors.BLUE, size=13)]
                            page.update()

                        def do_cancel_merge(e2):
                            merge_dlg.open = False
                            page.update()

                        merge_dlg = ft.AlertDialog(
                            modal=True,
                            title=ft.Text(f"合并人物「{ch_name}」"),
                            content=ft.Column(
                                [
                                    ft.Text(f"将「{ch_name}」作为别名添加到已有人物：", size=13),
                                    dd,
                                ],
                                tight=True,
                                spacing=10,
                            ),
                            actions=[
                                ft.TextButton("取消", on_click=do_cancel_merge),
                                ft.ElevatedButton("确认合并", on_click=do_merge),
                            ],
                        )
                        page.overlay.append(merge_dlg)
                        merge_dlg.open = True
                        page.update()

                    return handler

                def make_ignore_char(ch_name, row_ref):
                    def handler(e):
                        app_state.ignore_entity(EntityKind.character, ch_name)
                        show_snackbar(f"已忽略人物「{ch_name}」", ft.Colors.GREY)
                        row_ref.controls = [ft.Text("已忽略", color=ft.Colors.GREY, size=13)]
                        page.update()

                    return handler

                action_row.controls = [
                    ft.OutlinedButton(
                        "添加", icon=ft.Icons.PERSON_ADD, on_click=make_add_char(name, action_row)
                    ),
                    ft.OutlinedButton(
                        "合并", icon=ft.Icons.MERGE, on_click=make_merge_char(name, action_row)
                    ),
                    ft.TextButton(
                        "忽略",
                        on_click=make_ignore_char(name, action_row),
                        style=ft.ButtonStyle(color=ft.Colors.GREY),
                    ),
                ]
                right_controls.append(action_row)

            content_controls.append(
                ft.Row(
                    controls=[
                        ft.Row(controls=row_controls, spacing=8),
                        ft.Row(controls=right_controls),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )

    # --- Locations ---
    if locs_mentioned:
        content_controls.append(ft.Divider())
        content_controls.append(
            ft.Text(
                f"📍 地点 ({len(locs_mentioned)})",
                size=16,
                weight=ft.FontWeight.BOLD,
            )
        )
        for lo in locs_mentioned:
            name = lo.get("name", "未知")
            is_new = lo.get("is_new", False)
            context = lo.get("context", "")
            row_controls: list[ft.Control] = [ft.Text(name, weight=ft.FontWeight.BOLD)]
            if is_new:
                row_controls.append(
                    ft.Container(
                        content=ft.Text("新发现", size=11, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.ORANGE,
                        border_radius=4,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    )
                )
            if context:
                row_controls.append(ft.Text(context, size=12, color=ft.Colors.GREY))

            right_controls: list[ft.Control] = []
            if is_new:
                action_row = ft.Row(spacing=4)

                def make_add_loc(lo_name, row_ref):
                    def handler(e):
                        app_state.add_location(name=lo_name)
                        show_snackbar(f"已添加地点「{lo_name}」", ft.Colors.GREEN)
                        row_ref.controls = [ft.Text("已添加", color=ft.Colors.GREEN, size=13)]
                        page.update()

                    return handler

                def make_merge_loc(lo_name, row_ref):
                    def handler(e):
                        locs = (
                            app_state.current_project.locations if app_state.current_project else []
                        )
                        if not locs:
                            show_snackbar("项目中暂无地点可合并", ft.Colors.AMBER)
                            return
                        dd = ft.Dropdown(
                            label="合并到",
                            options=[ft.dropdown.Option(key=lo.id, text=lo.name) for lo in locs],
                            width=200,
                        )

                        def do_merge(e2):
                            if not dd.value:
                                show_snackbar("请选择目标地点", ft.Colors.AMBER)
                                return
                            app_state.merge_location(lo_name, dd.value)
                            target = next(
                                (
                                    lo
                                    for lo in app_state.current_project.locations
                                    if lo.id == dd.value
                                ),
                                None,
                            )
                            show_snackbar(
                                f"已将「{lo_name}」合并为「{target.name if target else dd.value}」的别名",
                                ft.Colors.GREEN,
                            )
                            merge_dlg.open = False
                            row_ref.controls = [ft.Text("已合并", color=ft.Colors.BLUE, size=13)]
                            page.update()

                        def do_cancel_merge(e2):
                            merge_dlg.open = False
                            page.update()

                        merge_dlg = ft.AlertDialog(
                            modal=True,
                            title=ft.Text(f"合并地点「{lo_name}」"),
                            content=ft.Column(
                                [
                                    ft.Text(f"将「{lo_name}」作为别名添加到已有地点：", size=13),
                                    dd,
                                ],
                                tight=True,
                                spacing=10,
                            ),
                            actions=[
                                ft.TextButton("取消", on_click=do_cancel_merge),
                                ft.ElevatedButton("确认合并", on_click=do_merge),
                            ],
                        )
                        page.overlay.append(merge_dlg)
                        merge_dlg.open = True
                        page.update()

                    return handler

                def make_ignore_loc(lo_name, row_ref):
                    def handler(e):
                        app_state.ignore_entity(EntityKind.location, lo_name)
                        show_snackbar(f"已忽略地点「{lo_name}」", ft.Colors.GREY)
                        row_ref.controls = [ft.Text("已忽略", color=ft.Colors.GREY, size=13)]
                        page.update()

                    return handler

                action_row.controls = [
                    ft.OutlinedButton(
                        "添加", icon=ft.Icons.ADD_LOCATION, on_click=make_add_loc(name, action_row)
                    ),
                    ft.OutlinedButton(
                        "合并", icon=ft.Icons.MERGE, on_click=make_merge_loc(name, action_row)
                    ),
                    ft.TextButton(
                        "忽略",
                        on_click=make_ignore_loc(name, action_row),
                        style=ft.ButtonStyle(color=ft.Colors.GREY),
                    ),
                ]
                right_controls.append(action_row)

            content_controls.append(
                ft.Row(
                    controls=[
                        ft.Row(controls=row_controls, spacing=8),
                        ft.Row(controls=right_controls),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )

    # --- Time references ---
    if time_refs:
        content_controls.append(ft.Divider())
        content_controls.append(
            ft.Text(
                f"🕐 时间引用 ({len(time_refs)})",
                size=16,
                weight=ft.FontWeight.BOLD,
            )
        )
        for tr in time_refs:
            ts = tr.get("time_slot", "?")
            ref = tr.get("reference_text", "")
            explicit = tr.get("is_explicit", False)
            is_valid_ts = bool(ts and re.match(r"^\d{2}:\d{2}$", ts))
            is_new_ts = is_valid_ts and ts not in existing_time_slots

            row_controls: list[ft.Control] = []
            if ts:
                row_controls.append(
                    ft.Container(
                        content=ft.Text(ts, size=12, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.BLUE,
                        border_radius=4,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    )
                )
            row_controls.append(ft.Text(ref, size=13))
            if explicit:
                row_controls.append(
                    ft.Container(
                        content=ft.Text("明确", size=11, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.GREEN,
                        border_radius=4,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    )
                )
            if is_new_ts:
                row_controls.append(
                    ft.Container(
                        content=ft.Text("新发现", size=11, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.ORANGE,
                        border_radius=4,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    )
                )

            right_controls: list[ft.Control] = []
            if is_new_ts:
                action_row = ft.Row(spacing=4)

                def make_add_time(time_slot, row_ref):
                    def handler(e):
                        try:
                            app_state.add_time_slot(time_slot)
                            show_snackbar(f"已添加时间段「{time_slot}」", ft.Colors.GREEN)
                            row_ref.controls = [ft.Text("已添加", color=ft.Colors.GREEN, size=13)]
                        except ValueError as exc:
                            show_snackbar(str(exc), ft.Colors.AMBER)
                        page.update()

                    return handler

                def make_ignore_time(time_slot, row_ref):
                    def handler(e):
                        app_state.ignore_entity(EntityKind.time_slot, time_slot)
                        show_snackbar(f"已忽略时间段「{time_slot}」", ft.Colors.GREY)
                        row_ref.controls = [ft.Text("已忽略", color=ft.Colors.GREY, size=13)]
                        page.update()

                    return handler

                action_row.controls = [
                    ft.OutlinedButton(
                        "添加", icon=ft.Icons.MORE_TIME, on_click=make_add_time(ts, action_row)
                    ),
                    ft.TextButton(
                        "忽略",
                        on_click=make_ignore_time(ts, action_row),
                        style=ft.ButtonStyle(color=ft.Colors.GREY),
                    ),
                ]
                right_controls.append(action_row)

            content_controls.append(
                ft.Row(
                    controls=[
                        ft.Row(controls=row_controls, spacing=8),
                        ft.Row(controls=right_controls),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )

    # --- Direct facts (deductions) ---
    if direct_facts:
        content_controls.append(ft.Divider())
        content_controls.append(
            ft.Row(
                controls=[
                    ft.Text(
                        f"📋 可添加的推断 ({len(direct_facts)})",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
            )
        )

        add_all_facts_btn = ft.ElevatedButton(
            "全部添加到审查队列",
            icon=ft.Icons.PLAYLIST_ADD_CHECK,
        )

        def add_all_facts_handler(e):
            created = _create_deductions_from_facts(proj, direct_facts, script_id)
            if created > 0:
                show_snackbar(f"已将 {created} 条推断加入审查队列", ft.Colors.GREEN)
            elif len(direct_facts) == 0:
                show_snackbar("没有可添加的推断", ft.Colors.AMBER)
            else:
                show_snackbar("所有推断均已存在或实体未匹配，无新增内容", ft.Colors.AMBER)
            add_all_facts_btn.disabled = True
            add_all_facts_btn.text = "已添加"
            page.update()

        add_all_facts_btn.on_click = add_all_facts_handler
        content_controls.append(add_all_facts_btn)

        content_controls.append(
            ft.Text(
                "💡 点击「添加到审查」将推断加入审查队列，或点击「全部添加」一次性添加",
                size=12,
                color=ft.Colors.GREY,
            )
        )

        for idx, df in enumerate(direct_facts):
            char_n = df.get("character_name", "?")
            loc_n = df.get("location_name", "?")
            ts = df.get("time_slot", "?")
            conf = df.get("confidence", "medium")
            evidence = df.get("evidence", "")

            # Check if character and location can be resolved
            char = next((c for c in proj.characters if c.name.lower() == char_n.lower()), None)
            loc = next(
                (loc_obj for loc_obj in proj.locations if loc_obj.name.lower() == loc_n.lower()),
                None,
            )
            can_resolve = char is not None and loc is not None

            def make_add_single_fact(fact_dict, btn_ref):
                def handler(e):
                    success = _create_single_deduction(proj, fact_dict, script_id)
                    if success:
                        show_snackbar("已添加到审查队列", ft.Colors.GREEN)
                        btn_ref.disabled = True
                        btn_ref.text = "已添加"
                    else:
                        show_snackbar("无法添加：请先添加对应的人物和地点", ft.Colors.AMBER)
                    page.update()

                return handler

            fact_row_controls: list[ft.Control] = [
                ft.Text(f"👤 {char_n}", weight=ft.FontWeight.BOLD),
                ft.Text(f"📍 {loc_n}"),
            ]
            if ts:
                fact_row_controls.append(
                    ft.Container(
                        content=ft.Text(ts, size=12, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.BLUE,
                        border_radius=4,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    )
                )
            fact_row_controls.append(
                ft.Container(
                    content=ft.Text(conf, size=11, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.GREY,
                    border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                )
            )

            add_fact_btn = ft.OutlinedButton(
                "添加到审查",
                icon=ft.Icons.ADD_TASK,
                disabled=not can_resolve,
                tooltip=None if can_resolve else "请先添加对应的人物和地点",
            )
            if can_resolve:
                add_fact_btn.on_click = make_add_single_fact(df, add_fact_btn)

            fact_card_controls: list[ft.Control] = [
                ft.Row(
                    controls=[
                        ft.Row(controls=fact_row_controls, spacing=8),
                        add_fact_btn,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ]
            if evidence:
                fact_card_controls.append(ft.Text(evidence, size=12, color=ft.Colors.GREY))

            content_controls.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(controls=fact_card_controls, spacing=4),
                        padding=12,
                    ),
                )
            )

    # Empty state for analysis
    if not chars_mentioned and not locs_mentioned and not time_refs and not direct_facts:
        content_controls.append(ft.Text("未提取到有效信息", color=ft.Colors.GREY, size=14))

    # Navigation hint
    if direct_facts:
        content_controls.append(ft.Divider())
        content_controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LIGHTBULB, color=ft.Colors.BLUE),
                        ft.Text(
                            "💡 提示：添加推断后，请前往「审查」标签页确认 AI 提取的推断结果",
                            size=13,
                            color=ft.Colors.BLUE,
                        ),
                    ],
                    spacing=8,
                ),
                bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.BLUE),
                border_radius=4,
                padding=10,
            )
        )

    def close_dialog(e):
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Text("📊 剧本分析结果"),
        content=ft.Container(
            content=ft.Column(
                controls=content_controls,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=560,
            height=500,
        ),
        actions=[ft.TextButton("关闭", on_click=close_dialog)],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()


# ---------------------------------------------------------------------------
# Delete confirmation dialog
# ---------------------------------------------------------------------------


def _confirm_delete_script(
    page: ft.Page,
    script_id: str,
    script_title: str,
    refresh,
    show_snackbar,
):
    """Show a confirmation dialog before deleting a script."""

    def do_delete(e):
        app_state.remove_script(script_id)
        show_snackbar("删除成功", ft.Colors.GREEN)
        dlg.open = False
        page.update()
        refresh()

    def do_cancel(e):
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Text(f"确认删除剧本「{script_title}」？"),
        content=ft.Text("此操作不可撤销", color=ft.Colors.GREY),
        actions=[
            ft.TextButton("取消", on_click=do_cancel),
            ft.ElevatedButton(
                "删除",
                on_click=do_delete,
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.RED,
            ),
        ],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()


# ---------------------------------------------------------------------------
# Async AI analysis
# ---------------------------------------------------------------------------


async def _run_script_analysis(
    page: ft.Page,
    script_id: str,
    refresh,
    show_snackbar,
    on_complete=None,
):
    """Run AI analysis on a specific script and show results."""
    proj = app_state.current_project
    if not proj:
        return

    script = next((s for s in proj.scripts if s.id == script_id), None)
    if not script:
        show_snackbar("找不到剧本", ft.Colors.AMBER)
        return

    # Show progress
    logger.info("scripts: starting analyze_script for script_id={!r}", script_id)
    show_snackbar("🤖 正在分析剧本...", ft.Colors.BLUE)

    try:
        from src.services.deduction import DeductionService

        service = DeductionService()
        result = await service.analyze_script(proj, script)

        app_state.save_script_analysis(script_id, result)
        logger.info(
            "scripts: analyze_script done script_id={!r} direct_facts={}",
            script_id,
            len(result.get("direct_facts", [])),
        )
        if on_complete:
            try:
                on_complete()
            except Exception:
                pass
        refresh()
        _show_analysis_results_dialog(page, proj, result, script_id, refresh, show_snackbar)
    except ValueError as e:
        logger.exception("scripts: analyze_script ValueError for script_id={!r}", script_id)
        show_snackbar(str(e), ft.Colors.RED)
    except Exception as e:
        logger.exception("scripts: analyze_script failed for script_id={!r}", script_id)
        show_snackbar(f"剧本分析失败: {str(e)[:200]}", ft.Colors.RED)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _script_header(script) -> str:
    """Build a summary line for a script expansion header."""
    title = script.title or "无标题剧本"
    time_str = script.added_at.strftime("%m-%d %H:%M")
    preview = script.raw_text[:80].replace("\n", " ")
    if len(script.raw_text) > 80:
        preview += "..."
    return f"{title} — {time_str} | {preview}"
