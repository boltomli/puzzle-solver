"""剧本管理页面 — Scripts tab.

Allows adding, viewing, and deleting scripts (scene text from the game).
"""

import re

from src.models.puzzle import ConfidenceLevel, Deduction, DeductionStatus
from src.services.config import load_config
from src.ui.state import app_state


def _is_api_configured() -> bool:
    """Check if API is configured for AI features."""
    config = load_config()
    return bool(config.get("api_base_url") and config.get("model"))


def scripts_tab_content():
    """Render the scripts management tab content."""
    from nicegui import ui

    with ui.column().classes("w-full q-pa-md gap-4"):
        ui.label("剧本管理").classes("text-h5")

        # API not configured banner (A3.3)
        if not _is_api_configured():
            with ui.card().classes("w-full q-pa-sm").style(
                "border: 1px solid #ff9800; background-color: rgba(255, 152, 0, 0.08);"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("warning", color="warning")
                    ui.label("API 未配置，AI 功能（自动分析、推断）暂不可用。").classes(
                        "text-body2"
                    )
                    ui.label("请前往「设置」页面配置 API。").classes(
                        "text-body2 text-weight-bold"
                    )

        # --- Add Script Section ---
        with ui.card().classes("w-full"):
            with ui.card_section():
                ui.label("添加新剧本").classes("text-h6")

            with ui.card_section():
                title_input = ui.input(
                    label="标题（可选）",
                    placeholder="例如：第一幕、Alice的剧本",
                ).classes("w-full")

                raw_text_input = ui.textarea(
                    label="剧本文本 *",
                    placeholder="在此粘贴剧本文本...",
                ).classes("w-full").props("rows=8")

                # Ctrl+Enter to save shortcut
                raw_text_input.on(
                    "keydown.ctrl.enter",
                    lambda: save_script(),
                )

                notes_input = ui.input(
                    label="备注（可选）",
                    placeholder="你的备注或观察",
                ).classes("w-full")

                async def save_script():
                    text = raw_text_input.value.strip()
                    if not text:
                        ui.notify("请输入剧本文本", type="warning")
                        return

                    # Check if project is empty before saving (for auto-trigger)
                    proj = app_state.current_project
                    project_is_empty = (
                        proj is not None
                        and not proj.characters
                        and not proj.locations
                        and not proj.time_slots
                    )

                    script = app_state.add_script(
                        raw_text=text,
                        title=title_input.value.strip() or None,
                        user_notes=notes_input.value.strip() or None,
                    )
                    # Clear inputs
                    title_input.value = ""
                    raw_text_input.value = ""
                    notes_input.value = ""
                    ui.notify("剧本已保存", type="positive")
                    script_list.refresh()

                    # Auto-trigger script analysis on empty project
                    if project_is_empty:
                        if _is_api_configured():
                            await _run_script_analysis(script.id, on_complete=script_list.refresh)
                        else:
                            ui.notify(
                                "请先在设置页面配置 API，以启用自动剧本分析",
                                type="info",
                                timeout=5000,
                            )

                with ui.row().classes("items-center gap-2"):
                    ui.button(
                        "保存剧本",
                        on_click=save_script,
                        icon="save",
                    ).props("color=primary")
                    ui.label("Ctrl+Enter 快捷保存").classes("text-caption text-grey")

        # --- Script List Section ---
        @ui.refreshable
        def script_list():
            if not app_state.current_project:
                return

            scripts = app_state.current_project.scripts
            if not scripts:
                with ui.card().classes("w-full q-pa-lg text-center"):
                    ui.icon("description", size="3em", color="grey")
                    ui.label("暂无剧本").classes("text-body1 text-grey q-mt-sm")
                    ui.label("请在上方添加剧本文本，AI 将帮助您提取人物、地点等信息").classes(
                        "text-caption text-grey"
                    )
                return

            ui.label(f"已有 {len(scripts)} 个剧本").classes("text-subtitle1")

            for script in reversed(scripts):  # Show newest first
                with ui.card().classes("w-full"):
                    with ui.expansion(
                        text=_script_header(script),
                        icon="description",
                    ).classes("w-full") as expansion:
                        # Full text display
                        with ui.column().classes("w-full gap-2"):
                            if script.metadata.user_notes:
                                ui.label(f"📝 备注: {script.metadata.user_notes}").classes(
                                    "text-body2 text-grey"
                                )
                            if script.metadata.stated_time:
                                ui.label(
                                    f"🕐 时间: {script.metadata.stated_time}"
                                ).classes("text-body2")
                            if script.metadata.stated_location:
                                ui.label(
                                    f"📍 地点: {script.metadata.stated_location}"
                                ).classes("text-body2")

                            ui.separator()
                            # Show full text in a code-like block
                            ui.html(
                                f'<pre style="white-space: pre-wrap; word-wrap: break-word; '
                                f'font-family: inherit; margin: 0; padding: 8px; '
                                f'background: rgba(255,255,255,0.05); border-radius: 4px;">'
                                f"{_escape_html(script.raw_text)}</pre>"
                            ).classes("w-full")

                            # Action buttons row
                            with ui.row().classes("justify-end gap-2"):
                                api_ok = _is_api_configured()

                                def make_analyze_handler(s_id):
                                    async def handler():
                                        await _run_script_analysis(s_id, on_complete=script_list.refresh)
                                    return handler

                                def make_view_results_handler(s_proj, s_result, s_id):
                                    def handler():
                                        _show_analysis_results_dialog(s_proj, s_result, s_id)
                                    return handler

                                if script.analysis_result is not None:
                                    # Has cached results — show view + re-analyze
                                    ui.button(
                                        "📊 查看分析结果",
                                        on_click=make_view_results_handler(
                                            app_state.current_project,
                                            script.analysis_result,
                                            script.id,
                                        ),
                                        icon="assessment",
                                    ).props("color=positive dense")

                                    reanalyze_btn = ui.button(
                                        "🔄 重新分析",
                                        on_click=make_analyze_handler(script.id),
                                        icon="refresh",
                                    ).props(
                                        f"{'color=secondary' if api_ok else 'color=grey disabled'} dense outline size=sm"
                                    )
                                    if not api_ok:
                                        reanalyze_btn.tooltip("请先在设置页面配置 API")
                                else:
                                    # No cached results — show analyze button
                                    analyze_btn = ui.button(
                                        "🤖 分析此剧本",
                                        on_click=make_analyze_handler(script.id),
                                        icon="psychology",
                                    ).props(
                                        f"{'color=secondary' if api_ok else 'color=grey disabled'} dense outline"
                                    )
                                    if not api_ok:
                                        analyze_btn.tooltip("请先在设置页面配置 API")

                                # Delete button
                                def make_delete_handler(s_id, s_title):
                                    def handler():
                                        _confirm_delete_script(s_id, s_title)
                                    return handler

                                ui.button(
                                    "删除",
                                    on_click=make_delete_handler(
                                        script.id,
                                        script.title or "无标题",
                                    ),
                                    icon="delete",
                                ).props("flat color=negative dense")

                    # Show preview text outside the expansion header area
                    preview = script.raw_text[:200]
                    if len(script.raw_text) > 200:
                        preview += "..."

        def _confirm_delete_script(script_id: str, script_title: str):
            """Show a confirmation dialog before deleting a script."""
            with ui.dialog() as dialog, ui.card():
                ui.label(f"确认删除剧本「{script_title}」？").classes("text-h6")
                ui.label("此操作不可撤销").classes("text-body2 text-grey")

                def do_delete():
                    app_state.remove_script(script_id)
                    ui.notify("删除成功", type="positive")
                    dialog.close()
                    script_list.refresh()

                with ui.row().classes("w-full justify-end q-mt-md"):
                    ui.button("取消", on_click=dialog.close).props("flat")
                    ui.button("删除", on_click=do_delete).props("color=negative")

            dialog.open()

        script_list()


async def _run_script_analysis(script_id: str, on_complete=None):
    """Run AI analysis on a specific script and show results."""
    from nicegui import ui
    proj = app_state.current_project
    if not proj:
        return

    script = next((s for s in proj.scripts if s.id == script_id), None)
    if not script:
        ui.notify("找不到剧本", type="warning")
        return

    spinner = ui.spinner("dots", size="lg", color="primary")
    try:
        from src.services.deduction import DeductionService

        service = DeductionService()
        ui.notify("🤖 正在分析剧本...", type="info")
        result = await service.analyze_script(proj, script)

        app_state.save_script_analysis(script_id, result)  # Cache it
        if on_complete:
            try:
                on_complete()
            except Exception:
                pass
        _show_analysis_results_dialog(proj, result, script_id)
    except ValueError as e:
        ui.notify(str(e), type="negative")
    except Exception as e:
        ui.notify(f"剧本分析失败: {str(e)[:200]}", type="negative", timeout=10000)
    finally:
        try:
            spinner.delete()
        except (RuntimeError, Exception):
            pass


def _show_analysis_results_dialog(proj, result: dict, script_id: str):
    """Show the script analysis results in a dialog."""
    from nicegui import ui
    chars_mentioned = result.get("characters_mentioned", [])
    locs_mentioned = result.get("locations_mentioned", [])
    time_refs = result.get("time_references", [])
    direct_facts = result.get("direct_facts", [])

    # Collect new entities for "Add All Entities" button
    new_chars = [ch for ch in chars_mentioned if ch.get("is_new", False)]
    new_locs = [lo for lo in locs_mentioned if lo.get("is_new", False)]
    # Collect new time slots (valid HH:MM that are not already in the project)
    existing_time_slots = set(proj.time_slots) if proj else set()
    new_time_refs = [
        tr for tr in time_refs
        if tr.get("time_slot")
        and re.match(r"^\d{2}:\d{2}$", tr["time_slot"])
        and tr["time_slot"] not in existing_time_slots
    ]

    # Track which facts have been added as deductions (by index)
    added_fact_indices: set[int] = set()

    with ui.dialog() as dlg, ui.card().classes("w-[600px] max-h-[80vh]"):
        ui.label("📊 剧本分析结果").classes("text-h6 q-mb-md")

        # --- "Add All Entities" button for bulk entity addition ---
        has_new_entities = new_chars or new_locs or new_time_refs
        if has_new_entities:
            def add_all_entities():
                added_count = 0
                for ch in new_chars:
                    ch_name = ch.get("name", "")
                    if ch_name:
                        # Skip if already exists (may have been added individually)
                        existing_names = {c.name for c in proj.characters}
                        if ch_name not in existing_names:
                            app_state.add_character(name=ch_name)
                            added_count += 1
                for lo in new_locs:
                    lo_name = lo.get("name", "")
                    if lo_name:
                        existing_names = {l.name for l in proj.locations}
                        if lo_name not in existing_names:
                            app_state.add_location(name=lo_name)
                            added_count += 1
                for tr in new_time_refs:
                    ts = tr.get("time_slot", "")
                    if ts and ts not in proj.time_slots:
                        try:
                            app_state.add_time_slot(ts)
                            added_count += 1
                        except ValueError:
                            pass
                ui.notify(
                    f"已批量添加 {added_count} 个实体（人物/地点/时间段）",
                    type="positive",
                )

            add_all_btn = ui.button(
                "全部添加实体",
                on_click=add_all_entities,
                icon="playlist_add",
            ).props("color=primary").classes("q-mb-md")
            add_all_btn.tooltip("仅添加新发现的人物、地点和时间段，不包含推断事实")

        # Characters found
        if chars_mentioned:
            ui.label(f"👤 人物 ({len(chars_mentioned)})").classes(
                "text-subtitle1 text-weight-bold q-mb-sm"
            )
            for ch in chars_mentioned:
                name = ch.get("name", "未知")
                is_new = ch.get("is_new", False)
                context = ch.get("context", "")
                with ui.row().classes("w-full items-center justify-between q-mb-xs"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(name).classes("text-body1")
                        if is_new:
                            ui.badge("新发现", color="orange").classes("text-caption")
                        if context:
                            ui.label(context).classes("text-caption text-grey")
                    if is_new:
                        def make_add_char(ch_name):
                            def handler():
                                app_state.add_character(name=ch_name)
                                ui.notify(f"已添加人物「{ch_name}」", type="positive")
                            return handler

                        ui.button(
                            "添加", on_click=make_add_char(name), icon="person_add"
                        ).props("dense color=primary outline size=sm")

        # Locations found
        if locs_mentioned:
            ui.separator().classes("q-my-sm")
            ui.label(f"📍 地点 ({len(locs_mentioned)})").classes(
                "text-subtitle1 text-weight-bold q-mb-sm"
            )
            for lo in locs_mentioned:
                name = lo.get("name", "未知")
                is_new = lo.get("is_new", False)
                context = lo.get("context", "")
                with ui.row().classes("w-full items-center justify-between q-mb-xs"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(name).classes("text-body1")
                        if is_new:
                            ui.badge("新发现", color="orange").classes("text-caption")
                        if context:
                            ui.label(context).classes("text-caption text-grey")
                    if is_new:
                        def make_add_loc(lo_name):
                            def handler():
                                app_state.add_location(name=lo_name)
                                ui.notify(f"已添加地点「{lo_name}」", type="positive")
                            return handler

                        ui.button(
                            "添加", on_click=make_add_loc(name), icon="add_location"
                        ).props("dense color=primary outline size=sm")

        # Time references (with add buttons)
        if time_refs:
            ui.separator().classes("q-my-sm")
            ui.label(f"🕐 时间引用 ({len(time_refs)})").classes(
                "text-subtitle1 text-weight-bold q-mb-sm"
            )
            for tr in time_refs:
                ts = tr.get("time_slot", "?")
                ref = tr.get("reference_text", "")
                explicit = tr.get("is_explicit", False)
                is_valid_ts = bool(ts and re.match(r"^\d{2}:\d{2}$", ts))
                is_new_ts = is_valid_ts and ts not in existing_time_slots
                with ui.row().classes("w-full items-center justify-between q-mb-xs"):
                    with ui.row().classes("items-center gap-2"):
                        if ts:
                            ui.badge(ts, color="primary").classes("text-body2")
                        ui.label(ref).classes("text-body2")
                        if explicit:
                            ui.badge("明确", color="positive").classes("text-caption")
                        if is_new_ts:
                            ui.badge("新发现", color="orange").classes("text-caption")
                    if is_new_ts:
                        def make_add_time(time_slot):
                            def handler():
                                try:
                                    app_state.add_time_slot(time_slot)
                                    ui.notify(f"已添加时间段「{time_slot}」", type="positive")
                                except ValueError as e:
                                    ui.notify(str(e), type="warning")
                            return handler

                        ui.button(
                            "添加", on_click=make_add_time(ts), icon="more_time"
                        ).props("dense color=primary outline size=sm")

        # Direct facts — user-controlled deduction creation
        if direct_facts:
            ui.separator().classes("q-my-sm")

            with ui.row().classes("w-full items-center justify-between q-mb-sm"):
                ui.label(f"📋 可添加的推断 ({len(direct_facts)})").classes(
                    "text-subtitle1 text-weight-bold"
                )

                def add_all_facts_handler():
                    created = _create_deductions_from_facts(
                        proj, direct_facts, script_id
                    )
                    if created > 0:
                        ui.notify(
                            f"已将 {created} 条推断加入审查队列",
                            type="positive",
                        )
                        # Mark all as added
                        for i in range(len(direct_facts)):
                            added_fact_indices.add(i)
                    else:
                        ui.notify(
                            "没有可添加的推断（请先添加对应的人物和地点）",
                            type="warning",
                        )

                ui.button(
                    "全部添加到审查队列",
                    on_click=add_all_facts_handler,
                    icon="playlist_add_check",
                ).props("dense color=secondary outline size=sm")

            ui.label(
                "💡 点击「添加到审查」将推断加入审查队列，或点击「全部添加」一次性添加"
            ).classes("text-caption text-grey q-mb-sm")

            for idx, df in enumerate(direct_facts):
                char_n = df.get("character_name", "?")
                loc_n = df.get("location_name", "?")
                ts = df.get("time_slot", "?")
                conf = df.get("confidence", "medium")
                evidence = df.get("evidence", "")

                with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(f"👤 {char_n}").classes("text-weight-bold")
                            ui.label(f"📍 {loc_n}")
                            if ts:
                                ui.badge(ts, color="primary")
                            ui.badge(conf, color="grey").classes("text-caption")

                        # Per-fact "添加到审查" button
                        def make_add_single_fact(fact_idx, fact_dict):
                            def handler(btn_ref=None):
                                # Check if character and location can be resolved
                                success = _create_single_deduction(
                                    proj, fact_dict, script_id
                                )
                                if success:
                                    added_fact_indices.add(fact_idx)
                                    ui.notify("已添加到审查队列", type="positive")
                                else:
                                    ui.notify(
                                        "无法添加：请先添加对应的人物和地点",
                                        type="warning",
                                    )
                            return handler

                        # Check if character and location can be resolved
                        char = next(
                            (c for c in proj.characters if c.name == char_n), None
                        )
                        loc = next(
                            (l for l in proj.locations if l.name == loc_n), None
                        )
                        can_resolve = char is not None and loc is not None

                        if can_resolve:
                            add_btn = ui.button(
                                "添加到审查",
                                on_click=make_add_single_fact(idx, df),
                                icon="add_task",
                            ).props("dense color=secondary outline size=sm")
                        else:
                            add_btn = ui.button(
                                "添加到审查",
                                icon="add_task",
                            ).props("dense color=grey disabled size=sm")
                            add_btn.tooltip("请先添加对应的人物和地点")

                    if evidence:
                        ui.label(evidence).classes("text-caption text-grey")

        if not chars_mentioned and not locs_mentioned and not time_refs and not direct_facts:
            ui.label("未提取到有效信息").classes("text-body1 text-grey")

        # Post-analysis navigation hint
        if direct_facts:
            ui.separator().classes("q-my-sm")
            with ui.row().classes("items-center gap-2 q-pa-sm").style(
                "background-color: rgba(33, 150, 243, 0.08); border-radius: 4px;"
            ):
                ui.icon("lightbulb", color="primary")
                ui.label(
                    "💡 提示：添加推断后，请前往「审查」标签页确认 AI 提取的推断结果"
                ).classes("text-body2 text-primary")

        with ui.row().classes("w-full justify-end q-mt-md"):
            ui.button("关闭", on_click=dlg.close).props("flat")

    dlg.open()


def _create_single_deduction(proj, fact_dict: dict, script_id: str) -> bool:
    """Convert a single direct_fact from analysis into a pending Deduction.

    Maps character_name and location_name back to IDs from the project.
    Returns True if the deduction was successfully created.
    """
    char_name = fact_dict.get("character_name", "")
    loc_name = fact_dict.get("location_name", "")
    ts = fact_dict.get("time_slot", "")
    confidence_str = fact_dict.get("confidence", "medium")
    evidence = fact_dict.get("evidence", "")

    # Map names to IDs
    char = next((c for c in proj.characters if c.name == char_name), None)
    loc = next((l for l in proj.locations if l.name == loc_name), None)

    # Skip if we can't resolve both character and location
    if not char or not loc:
        return False
    # Skip if time_slot is not valid
    if not ts or not re.match(r"^\d{2}:\d{2}$", ts):
        return False

    # Map confidence string to enum
    try:
        conf = ConfidenceLevel(confidence_str)
    except ValueError:
        conf = ConfidenceLevel.medium

    deduction = Deduction(
        character_id=char.id,
        location_id=loc.id,
        time_slot=ts,
        confidence=conf,
        reasoning=evidence or f"剧本分析：{char_name} 在 {ts} 位于 {loc_name}",
        supporting_script_ids=[script_id],
        status=DeductionStatus.pending,
    )
    app_state.add_deduction(deduction)
    return True


def _create_deductions_from_facts(
    proj, direct_facts: list[dict], script_id: str
) -> int:
    """Convert direct_facts from analysis into pending Deduction objects.

    Maps character_name and location_name back to IDs from the project.
    Returns the number of deductions successfully created.
    """
    created = 0
    for df in direct_facts:
        char_name = df.get("character_name", "")
        loc_name = df.get("location_name", "")
        ts = df.get("time_slot", "")
        confidence_str = df.get("confidence", "medium")
        evidence = df.get("evidence", "")

        # Map names to IDs
        char = next(
            (c for c in proj.characters if c.name == char_name), None
        )
        loc = next(
            (l for l in proj.locations if l.name == loc_name), None
        )

        # Skip if we can't resolve both character and location
        if not char or not loc:
            continue
        # Skip if time_slot is not valid
        if not ts or not re.match(r"^\d{2}:\d{2}$", ts):
            continue

        # Map confidence string to enum
        try:
            conf = ConfidenceLevel(confidence_str)
        except ValueError:
            conf = ConfidenceLevel.medium

        deduction = Deduction(
            character_id=char.id,
            location_id=loc.id,
            time_slot=ts,
            confidence=conf,
            reasoning=evidence or f"剧本分析：{char_name} 在 {ts} 位于 {loc_name}",
            supporting_script_ids=[script_id],
            status=DeductionStatus.pending,
        )
        app_state.add_deduction(deduction)
        created += 1

    return created


def _script_header(script) -> str:
    """Build a summary line for a script expansion header."""
    title = script.title or "无标题剧本"
    time_str = script.added_at.strftime("%m-%d %H:%M")
    preview = script.raw_text[:80].replace("\n", " ")
    if len(script.raw_text) > 80:
        preview += "..."
    return f"{title} — {time_str} | {preview}"


def _escape_html(text: str) -> str:
    """Escape HTML special characters for safe display."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
