"""推理矩阵页面 — Matrix tab (Flet version).

Displays a time × character matrix table showing where each character was at each time slot.
Supports AI deduction triggers, cascade elimination, and statistics.
"""

import flet as ft

from src.models.puzzle import (
    Deduction,
    DeductionStatus,
    Project,
    SourceType,
)
from src.services.config import load_config
from src.ui.state import app_state


# ---------------------------------------------------------------------------
# Pure logic helper — tested by tests/test_matrix.py
# ---------------------------------------------------------------------------


def _is_api_configured() -> bool:
    """Check if API is configured for AI features."""
    config = load_config()
    return bool(config.get("api_base_url") and config.get("model"))


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


def build_location_time_data(project: Project) -> list[dict]:
    """Build the location × time table data from a project.

    Each row represents a location. Columns are: location name + one per time slot.
    For each cell, stores the display value (character names) and a status suffix.

    This is a standalone testable function (not tied to UI).

    Returns:
        List of row dicts with keys:
        - 'id': location id
        - 'location': location name
        - '{time_slot}': display string (character names, confirmed first, pending in parens)
        - '{time_slot}_status': 'confirmed' | 'pending' | 'unknown'
    """
    if not project.locations:
        return []

    rows = []
    for loc in project.locations:
        row: dict = {"id": loc.id, "location": loc.name}
        for ts in project.time_slots:
            # Find all confirmed facts for this (location, time_slot)
            confirmed_char_ids = [
                f.character_id
                for f in project.facts
                if f.location_id == loc.id and f.time_slot == ts
            ]
            # Find all pending deductions for this (location, time_slot)
            pending_char_ids = [
                d.character_id
                for d in project.deductions
                if d.location_id == loc.id
                and d.time_slot == ts
                and d.status == DeductionStatus.pending
            ]

            # Build character name lookup
            char_by_id = {c.id: c.name for c in project.characters}

            # Get confirmed character names
            confirmed_names = [
                char_by_id[cid] for cid in confirmed_char_ids if cid in char_by_id
            ]
            # Get pending character names (not already confirmed at this cell)
            confirmed_set = set(confirmed_char_ids)
            pending_names = [
                char_by_id[cid]
                for cid in pending_char_ids
                if cid in char_by_id and cid not in confirmed_set
            ]

            # Combine display: confirmed names first, then pending in parentheses
            parts: list[str] = list(confirmed_names)
            if pending_names:
                parts.append(f"({', '.join(pending_names)})")

            display = ", ".join(parts)

            # Determine status
            if confirmed_names:
                status = "confirmed"
            elif pending_names:
                status = "pending"
            else:
                status = "unknown"

            row[ts] = display
            row[f"{ts}_status"] = status
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Flet UI builder
# ---------------------------------------------------------------------------


def build_matrix_tab(page: ft.Page) -> ft.Control:
    """Build and return the matrix tab control tree.

    Contains:
    - API not configured banner (when applicable)
    - Matrix DataTable with color-coded cells
    - AI deduction and cascade buttons
    - Statistics panel
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
        """Rebuild the matrix tab content after state changes."""
        outer_container.content = _build_content(page, refresh, _show_snackbar)
        page.update()

    outer_container.content = _build_content(page, refresh, _show_snackbar)
    return ft.Column(
        controls=[
            ft.Text("推理矩阵", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            outer_container,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        expand=True,
    )


def _build_content(page: ft.Page, refresh, show_snackbar) -> ft.Control:
    """Build the full matrix page content."""
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
                            "API 未配置，AI 推断功能暂不可用。请前往「设置」页面配置 API。",
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

    # --- Empty state ---
    if not proj.characters or not proj.time_slots:
        controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.GRID_ON, size=48, color=ft.Colors.GREY),
                        ft.Text(
                            "请先在「管理」页面添加人物和时间段",
                            size=16,
                            color=ft.Colors.GREY,
                        ),
                        ft.Text(
                            "矩阵需要至少一个人物和一个时间段才能显示",
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
        return ft.Column(controls=controls, spacing=12)

    # --- Action buttons ---
    api_ok = _is_api_configured()

    async def run_ai_deduction(e):
        """Trigger a full AI deduction pass."""
        progress = ft.ProgressRing(width=24, height=24)
        controls.insert(0, progress)
        page.update()
        try:
            from src.services.deduction import DeductionService
            from loguru import logger

            service = DeductionService()
            show_snackbar("🤖 正在进行 AI 推断...", ft.Colors.BLUE)
            result = await service.run_deduction(proj)
            deductions_data = result.get("deductions", [])
            contradictions = result.get("contradictions_detected", [])

            # Build lookup maps for validation
            char_by_id = {c.id: c for c in proj.characters}
            loc_by_id = {l.id: l for l in proj.locations}
            char_by_name = {c.name.lower(): c for c in proj.characters}
            loc_by_name = {l.name.lower(): l for l in proj.locations}

            count = 0
            # Collect unresolvable raw names/ids for the "add entities" dialog
            unknown_char_names: dict[str, str] = {}  # raw_id -> display name
            unknown_loc_names: dict[str, str] = {}

            for d_data in deductions_data:
                raw_char_id = d_data.get("character_id", "")
                raw_loc_id = d_data.get("location_id", "")

                char_obj = char_by_id.get(raw_char_id) or char_by_name.get(raw_char_id.lower())
                loc_obj = loc_by_id.get(raw_loc_id) or loc_by_name.get(raw_loc_id.lower())

                if not char_obj:
                    unknown_char_names[raw_char_id] = raw_char_id
                if not loc_obj:
                    unknown_loc_names[raw_loc_id] = raw_loc_id

                if not char_obj or not loc_obj:
                    logger.warning(
                        "run_ai_deduction: skipping unresolvable deduction "
                        "char_id={!r} loc_id={!r}",
                        raw_char_id, raw_loc_id,
                    )
                    continue

                ded = Deduction(
                    character_id=char_obj.id,
                    location_id=loc_obj.id,
                    time_slot=d_data.get("time_slot", "00:00"),
                    confidence=d_data.get("confidence", "medium"),
                    reasoning=d_data.get("reasoning", ""),
                    supporting_script_ids=d_data.get("supporting_script_ids", []),
                    depends_on_fact_ids=d_data.get("depends_on_fact_ids", []),
                )
                added = app_state.add_deduction(ded)
                if added:
                    count += 1

            # Also collect AI-reported new entities (merge with unresolvable ones)
            for ch in result.get("new_characters_detected", []):
                name = ch.get("name", "").strip()
                if name:
                    unknown_char_names[name] = name
            for lo in result.get("new_locations_detected", []):
                name = lo.get("name", "").strip()
                if name:
                    unknown_loc_names[name] = name

            logger.info(
                "run_ai_deduction: count={} unknown_chars={} unknown_locs={}",
                count, list(unknown_char_names.values()), list(unknown_loc_names.values()),
            )

            refresh()

            # Filter out already-registered entities
            existing_char_names = {c.name for c in proj.characters}
            existing_loc_names = {l.name for l in proj.locations}
            final_unknown_chars = [
                n for n in unknown_char_names.values() if n not in existing_char_names
            ]
            final_unknown_locs = [
                n for n in unknown_loc_names.values() if n not in existing_loc_names
            ]

            if final_unknown_chars or final_unknown_locs:
                _show_new_entities_dialog(
                    page,
                    [{"name": n} for n in final_unknown_chars],
                    [{"name": n} for n in final_unknown_locs],
                    run_ai_deduction,
                    refresh,
                    show_snackbar,
                )
            else:
                msg_parts = [f"AI 推断完成：新增 {count} 条推断"]
                if contradictions:
                    msg_parts.append(f"⚠️ 发现 {len(contradictions)} 个矛盾")
                show_snackbar("；".join(msg_parts), ft.Colors.GREEN)

        except ValueError as exc:
            show_snackbar(str(exc), ft.Colors.RED)
        except Exception as exc:
            show_snackbar(f"AI 推断失败: {str(exc)[:200]}", ft.Colors.RED)
        finally:
            try:
                controls.remove(progress)
                page.update()
            except (ValueError, Exception):
                pass

    def run_cascade_deduction(e):
        """Trigger local elimination-based cascade."""
        try:
            from src.services.deduction import DeductionService

            new_deds = DeductionService.run_cascade(proj)
            count = 0
            for ded in new_deds:
                if app_state.add_deduction(ded):
                    count += 1
            if count > 0:
                show_snackbar(
                    f"消元推断完成：新增 {count} 条确定推断",
                    ft.Colors.GREEN,
                )
            else:
                show_snackbar("消元推断未发现新的确定推断", ft.Colors.BLUE)
            refresh()
        except Exception as exc:
            show_snackbar(f"消元推断失败: {str(exc)[:200]}", ft.Colors.RED)

    ai_button = ft.ElevatedButton(
        "🤖 AI 推断",
        icon=ft.Icons.PSYCHOLOGY,
        on_click=run_ai_deduction if api_ok else None,
        disabled=not api_ok,
        tooltip=None if api_ok else "请先在设置页面配置 API",
    )
    cascade_button = ft.OutlinedButton(
        "🔄 消元推断",
        icon=ft.Icons.AUTO_FIX_HIGH,
        on_click=run_cascade_deduction,
    )

    controls.append(
        ft.Row(
            controls=[ai_button, cascade_button],
            spacing=10,
        )
    )

    # --- Matrix DataTable ---
    rows = build_matrix_data(proj)

    if not rows:
        controls.append(ft.Text("暂无数据", color=ft.Colors.GREY, size=14))
    else:
        # Build DataTable columns
        dt_columns = [
            ft.DataColumn(
                ft.Text("人物", weight=ft.FontWeight.BOLD),
            ),
        ]
        for ts in proj.time_slots:
            dt_columns.append(
                ft.DataColumn(
                    ft.Text(ts, weight=ft.FontWeight.BOLD),
                )
            )

        # Build DataTable rows
        dt_rows = []
        for row_data in rows:
            cells = [
                ft.DataCell(
                    ft.Text(
                        row_data["character"],
                        weight=ft.FontWeight.BOLD,
                    )
                ),
            ]
            for ts in proj.time_slots:
                value = row_data[ts]
                status = row_data[f"{ts}_status"]
                cells.append(_make_cell(value, status))
            dt_rows.append(ft.DataRow(cells=cells))

        data_table = ft.DataTable(
            columns=dt_columns,
            rows=dt_rows,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
            heading_row_color=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            column_spacing=20,
        )

        controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[data_table],
                    scroll=ft.ScrollMode.AUTO,
                ),
            )
        )

    # --- Statistics Panel ---
    controls.append(ft.Divider())
    controls.append(_build_statistics(proj))

    # --- Location × Time Matrix ---
    controls.append(ft.Divider())
    controls.append(
        ft.Text("地点 × 时间矩阵", size=18, weight=ft.FontWeight.BOLD)
    )

    loc_rows = build_location_time_data(proj)
    if not loc_rows:
        controls.append(ft.Text("暂无地点数据", color=ft.Colors.GREY, size=14))
    else:
        # Build DataTable columns: 地点 + one per time slot
        loc_columns = [
            ft.DataColumn(
                ft.Text("地点", weight=ft.FontWeight.BOLD),
            ),
        ]
        for ts in proj.time_slots:
            loc_columns.append(
                ft.DataColumn(
                    ft.Text(ts, weight=ft.FontWeight.BOLD),
                )
            )

        # Build DataTable rows
        loc_dt_rows = []
        for row_data in loc_rows:
            cells = [
                ft.DataCell(
                    ft.Text(
                        row_data["location"],
                        weight=ft.FontWeight.BOLD,
                    )
                ),
            ]
            for ts in proj.time_slots:
                value = row_data[ts]
                status = row_data[f"{ts}_status"]
                cells.append(_make_cell(value, status))
            loc_dt_rows.append(ft.DataRow(cells=cells))

        loc_data_table = ft.DataTable(
            columns=loc_columns,
            rows=loc_dt_rows,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
            heading_row_color=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            column_spacing=20,
        )

        controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[loc_data_table],
                    scroll=ft.ScrollMode.AUTO,
                ),
            )
        )

    return ft.Column(controls=controls, spacing=12)


def _make_cell(value: str, status: str) -> ft.DataCell:
    """Create a color-coded DataCell for the matrix table."""
    color_map = {
        "confirmed": ft.Colors.GREEN_100,
        "pending": ft.Colors.AMBER_100,
        "unknown": None,
    }
    text_color_map = {
        "confirmed": ft.Colors.GREEN_900,
        "pending": ft.Colors.AMBER_900,
        "unknown": ft.Colors.GREY,
    }
    bg = color_map.get(status)
    text_color = text_color_map.get(status, ft.Colors.GREY)
    display = value if value else "—"

    return ft.DataCell(
        ft.Container(
            content=ft.Text(
                display,
                color=text_color,
                weight=ft.FontWeight.BOLD if status == "confirmed" else None,
            ),
            bgcolor=bg,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border_radius=4,
        )
    )


def _build_statistics(proj: Project) -> ft.Control:
    """Build the statistics panel showing matrix fill progress."""
    total_cells = len(proj.characters) * len(proj.time_slots)
    if total_cells == 0:
        return ft.Container()

    confirmed = 0
    pending = 0
    for char in proj.characters:
        for ts in proj.time_slots:
            has_fact = any(
                f.character_id == char.id and f.time_slot == ts
                for f in proj.facts
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

    return ft.Card(
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        "📊 统计",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        controls=[
                            _stat_item(str(total_cells), "总计格数", None),
                            _stat_item(str(confirmed), "已确认", ft.Colors.GREEN),
                            _stat_item(str(pending), "待审查", ft.Colors.AMBER),
                            _stat_item(str(unknown), "未知", ft.Colors.GREY),
                            _stat_item(f"{progress:.0f}%", "完成度", ft.Colors.BLUE),
                        ],
                        spacing=40,
                        wrap=True,
                    ),
                    ft.ProgressBar(
                        value=progress / 100,
                        color=ft.Colors.BLUE,
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE),
                    ),
                ],
                spacing=12,
            ),
            padding=20,
        ),
    )


def _stat_item(value: str, label: str, color) -> ft.Control:
    """Build a single statistic display item."""
    return ft.Column(
        controls=[
            ft.Text(value, size=24, weight=ft.FontWeight.BOLD, color=color),
            ft.Text(label, size=12, color=ft.Colors.GREY),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=2,
    )


def _show_new_entities_dialog(
    page: ft.Page,
    new_chars: list[dict],
    new_locs: list[dict],
    rerun_deduction,
    refresh,
    show_snackbar,
):
    """Show a dialog listing newly discovered entities with checkboxes to add them.

    new_chars / new_locs: list of {"name": str} dicts, already filtered to
    only contain names not yet registered in the project.
    After adding, offers to re-run AI deduction immediately.
    """
    # --- Build checkbox rows ---
    char_checks: list[tuple[ft.Checkbox, str]] = []
    loc_checks: list[tuple[ft.Checkbox, str]] = []

    content_rows: list[ft.Control] = []

    if new_chars:
        content_rows.append(
            ft.Text("🆕 新发现的人物", size=15, weight=ft.FontWeight.BOLD)
        )
        for ch in new_chars:
            name = ch.get("name", "").strip()
            if not name:
                continue
            context = ch.get("context", "")
            cb = ft.Checkbox(label=name, value=True)
            char_checks.append((cb, name))
            row_controls: list[ft.Control] = [cb]
            if context:
                row_controls.append(
                    ft.Text(context, size=12, color=ft.Colors.GREY, expand=True)
                )
            content_rows.append(ft.Row(controls=row_controls, spacing=8))

    if new_locs:
        if new_chars:
            content_rows.append(ft.Divider())
        content_rows.append(
            ft.Text("🆕 新发现的地点", size=15, weight=ft.FontWeight.BOLD)
        )
        for lo in new_locs:
            name = lo.get("name", "").strip()
            if not name:
                continue
            context = lo.get("context", "")
            cb = ft.Checkbox(label=name, value=True)
            loc_checks.append((cb, name))
            row_controls = [cb]
            if context:
                row_controls.append(
                    ft.Text(context, size=12, color=ft.Colors.GREY, expand=True)
                )
            content_rows.append(ft.Row(controls=row_controls, spacing=8))

    if not char_checks and not loc_checks:
        return

    rerun_check = ft.Checkbox(label="添加后立即重新推断", value=True)
    content_rows.append(ft.Divider())
    content_rows.append(rerun_check)

    def do_add(e):
        added = 0
        for cb, name in char_checks:
            if cb.value:
                existing = {c.name for c in app_state.current_project.characters}
                if name not in existing:
                    app_state.add_character(name=name)
                    added += 1
        for cb, name in loc_checks:
            if cb.value:
                existing = {l.name for l in app_state.current_project.locations}
                if name not in existing:
                    app_state.add_location(name=name)
                    added += 1
        dlg.open = False
        page.update()
        refresh()
        show_snackbar(f"已添加 {added} 个实体", ft.Colors.GREEN)
        if rerun_check.value and added > 0:
            page.run_task(rerun_deduction, None)

    def do_cancel(e):
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Text("🆕 AI 发现了新实体"),
        content=ft.Container(
            content=ft.Column(
                controls=content_rows,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=480,
            height=min(80 + 48 * (len(char_checks) + len(loc_checks)), 500),
        ),
        actions=[
            ft.TextButton("跳过", on_click=do_cancel),
            ft.ElevatedButton(
                "添加选中实体",
                icon=ft.Icons.PLAYLIST_ADD,
                on_click=do_add,
            ),
        ],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
