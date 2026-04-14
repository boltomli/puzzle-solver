"""推断审查页面 — Review tab (Flet version).

Displays pending deductions for user to accept, reject, or skip.
Sorted by confidence: certain → high → medium → low.
Shows deduction history (accepted/rejected) in a collapsible section.
"""

import flet as ft

from src.models.puzzle import ConfidenceLevel, DeductionStatus
from src.services.deduction import DeductionService
from src.ui.state import app_state

# Confidence display order and styling
_CONFIDENCE_ORDER = {
    ConfidenceLevel.certain: 0,
    ConfidenceLevel.high: 1,
    ConfidenceLevel.medium: 2,
    ConfidenceLevel.low: 3,
}

_CONFIDENCE_LABELS = {
    ConfidenceLevel.certain: "确定",
    ConfidenceLevel.high: "高",
    ConfidenceLevel.medium: "中",
    ConfidenceLevel.low: "低",
}

_CONFIDENCE_COLORS = {
    ConfidenceLevel.certain: ft.Colors.GREEN,
    ConfidenceLevel.high: ft.Colors.BLUE,
    ConfidenceLevel.medium: ft.Colors.AMBER,
    ConfidenceLevel.low: ft.Colors.GREY,
}


def build_review_tab(page: ft.Page) -> ft.Control:
    """Build the deduction review tab content.

    Returns a scrollable Column with pending deductions, batch actions,
    and deduction history.
    """
    proj = app_state.current_project
    if not proj:
        return ft.Column(
            controls=[
                ft.Text("推断审查", size=24, weight=ft.FontWeight.BOLD),
                ft.Text("请先选择或创建一个项目", color=ft.Colors.GREY),
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    # --- Outer container holds the live content; refresh() swaps it in-place ---
    outer_container = ft.Container(expand=True)

    def refresh():
        outer_container.content = _build_content(page, refresh)
        page.update()

    outer_container.content = _build_content(page, refresh)

    return ft.Column(
        controls=[
            ft.Text("推断审查", size=28, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            outer_container,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        expand=True,
    )


def _build_content(page: ft.Page, refresh) -> ft.Control:
    """Build the live inner content of the review tab (pending cards + history)."""
    proj = app_state.current_project
    if not proj:
        return ft.Text("请先选择或创建一个项目", color=ft.Colors.GREY)

    # Use centralized CacheManager indexes
    cache = app_state.cache

    # --- Pending deductions ---
    pending = [d for d in proj.deductions if d.status == DeductionStatus.pending]
    pending.sort(key=lambda d: _CONFIDENCE_ORDER.get(d.confidence, 99))

    controls: list[ft.Control] = []

    if not pending:
        controls.append(
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE,
                                size=48,
                                color=ft.Colors.GREEN,
                            ),
                            ft.Text(
                                "暂无待审查的推断",
                                size=16,
                                color=ft.Colors.GREY,
                            ),
                            ft.Text(
                                "可在「矩阵」页面触发 AI 推断或消元推断",
                                size=12,
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
    else:
        controls.append(ft.Text(f"共 {len(pending)} 条待审查推断", size=16))

        def on_clear_all_click(e):
            def do_clear(e):
                count = app_state.clear_pending_deductions()
                page.snack_bar = ft.SnackBar(ft.Text(f"已清除 {count} 条待审查推断"))
                page.snack_bar.open = True
                dlg.open = False
                page.update()
                refresh()

            def do_cancel(e):
                dlg.open = False
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text("确认清除"),
                content=ft.Text(f"确定要清除所有 {len(pending)} 条待审查推断吗？此操作不可撤销。"),
                actions=[
                    ft.TextButton("取消", on_click=do_cancel),
                    ft.ElevatedButton(
                        "确认清除",
                        bgcolor=ft.Colors.RED,
                        color=ft.Colors.WHITE,
                        on_click=do_clear,
                    ),
                ],
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        controls.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "清除所有待审查",
                        icon=ft.Icons.CLEAR_ALL,
                        style=ft.ButtonStyle(color=ft.Colors.RED),
                        on_click=on_clear_all_click,
                    ),
                ],
            )
        )

        # --- Deduction cards ---
        for ded in pending:
            char_obj = cache.char_by_id.get(ded.character_id)
            char_name = char_obj.name if char_obj else ded.character_id[:8]
            loc_obj = cache.loc_by_id.get(ded.location_id)
            loc_name = loc_obj.name if loc_obj else ded.location_id[:8]
            ts_label = app_state.get_time_slot_label(ded.time_slot)
            conf_label = _CONFIDENCE_LABELS.get(ded.confidence, str(ded.confidence))
            conf_color = _CONFIDENCE_COLORS.get(ded.confidence, ft.Colors.GREY)

            confidence_badge = ft.Container(
                content=ft.Text(
                    f"置信度: {conf_label}",
                    size=12,
                    color=ft.Colors.WHITE,
                ),
                bgcolor=conf_color,
                border_radius=12,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            )

            header_row = ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LIGHTBULB, color=ft.Colors.AMBER),
                    ft.Text("推断", size=18, weight=ft.FontWeight.BOLD),
                    confidence_badge,
                ],
                spacing=8,
            )

            entity_row = ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text("人物", size=12, color=ft.Colors.GREY),
                            ft.Text(char_name, size=16, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=2,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text("地点", size=12, color=ft.Colors.GREY),
                            ft.Text(loc_name, size=16, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=2,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text("时间", size=12, color=ft.Colors.GREY),
                            ft.Text(ts_label, size=16, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=40,
            )

            card_controls: list[ft.Control] = [header_row, entity_row]
            if ded.reasoning:
                card_controls.append(
                    ft.Column(
                        controls=[
                            ft.Text("推理过程", size=12, color=ft.Colors.GREY),
                            ft.Text(ded.reasoning, size=14),
                        ],
                        spacing=4,
                    )
                )

            def make_accept_handler(ded_id):
                def handler(e):
                    fact = app_state.accept_deduction(ded_id)
                    if fact:
                        try:
                            new_deds = DeductionService.run_cascade(proj)
                            count = 0
                            for new_ded in new_deds:
                                if app_state.add_deduction(new_ded):
                                    count += 1
                            page.snack_bar = ft.SnackBar(
                                ft.Text(f"已接受推断。消元发现 {count} 条新推断")
                            )
                            page.snack_bar.open = True
                        except Exception as exc:
                            page.snack_bar = ft.SnackBar(
                                ft.Text(f"已接受推断，但消元推断出错: {exc}"),
                                bgcolor=ft.Colors.AMBER,
                            )
                            page.snack_bar.open = True
                    else:
                        page.snack_bar = ft.SnackBar(
                            ft.Text("操作失败：推断未找到"),
                            bgcolor=ft.Colors.RED,
                        )
                        page.snack_bar.open = True
                    refresh()

                return handler

            def make_reject_handler(ded_id, d_char, d_loc, d_ts_label):
                def handler(e):
                    _show_reject_dialog(page, ded_id, d_char, d_loc, d_ts_label, refresh)

                return handler

            action_row = ft.Row(
                controls=[
                    ft.ElevatedButton(
                        "✅ 接受",
                        bgcolor=ft.Colors.GREEN,
                        color=ft.Colors.WHITE,
                        on_click=make_accept_handler(ded.id),
                    ),
                    ft.OutlinedButton(
                        "❌ 拒绝",
                        style=ft.ButtonStyle(color=ft.Colors.RED),
                        on_click=make_reject_handler(ded.id, char_name, loc_name, ts_label),
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=10,
            )
            card_controls.append(action_row)

            controls.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(controls=card_controls, spacing=12),
                        padding=20,
                    ),
                )
            )

    # --- Deduction History ---
    history_control = _build_deduction_history(proj, cache)
    if history_control:
        controls.append(ft.Divider())
        controls.append(history_control)

    return ft.Column(controls=controls, spacing=12)


def _build_deduction_history(proj, cache) -> ft.Control | None:
    """Build the deduction history section as an ExpansionTile.

    Shows resolved (accepted/rejected) deductions sorted by resolved_at descending.
    Returns None if no resolved deductions exist.

    Args:
        proj: The current project.
        cache: CacheManager instance for centralized index lookups.
    """
    resolved = [
        d
        for d in proj.deductions
        if d.status in (DeductionStatus.accepted, DeductionStatus.rejected)
    ]

    if not resolved:
        return None

    # Sort by resolved_at descending (most recent first)
    resolved.sort(key=lambda d: d.resolved_at or d.created_at, reverse=True)

    # Use centralized rejection_map from CacheManager
    rejection_map = cache.rejection_map

    history_items: list[ft.Control] = [
        ft.Text(
            f"共 {len(resolved)} 条已处理推断",
            size=14,
            color=ft.Colors.GREY,
        ),
    ]

    for ded in resolved:
        char_obj = cache.char_by_id.get(ded.character_id)
        char_name = char_obj.name if char_obj else ded.character_id[:8]
        loc_obj = cache.loc_by_id.get(ded.location_id)
        loc_name = loc_obj.name if loc_obj else ded.location_id[:8]
        ts_label = app_state.get_time_slot_label(ded.time_slot)
        conf_label = _CONFIDENCE_LABELS.get(ded.confidence, str(ded.confidence))
        conf_color = _CONFIDENCE_COLORS.get(ded.confidence, ft.Colors.GREY)

        is_accepted = ded.status == DeductionStatus.accepted
        status_label = "已接受" if is_accepted else "已拒绝"
        status_color = ft.Colors.GREEN if is_accepted else ft.Colors.RED
        status_icon = ft.Icons.CHECK_CIRCLE if is_accepted else ft.Icons.CANCEL

        # Status and confidence badges row
        badge_row = ft.Row(
            controls=[
                ft.Icon(status_icon, color=status_color, size=20),
                ft.Container(
                    content=ft.Text(status_label, size=12, color=ft.Colors.WHITE),
                    bgcolor=status_color,
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                ),
                ft.Container(
                    content=ft.Text(
                        f"置信度: {conf_label}",
                        size=12,
                        color=ft.Colors.WHITE,
                    ),
                    bgcolor=conf_color,
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                ),
            ],
            spacing=8,
        )
        if ded.resolved_at:
            badge_row.controls.append(
                ft.Text(
                    ded.resolved_at.strftime("%m-%d %H:%M"),
                    size=12,
                    color=ft.Colors.GREY,
                )
            )

        # Entity info
        entity_row = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text("人物", size=12, color=ft.Colors.GREY),
                        ft.Text(
                            char_name,
                            size=14,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=2,
                ),
                ft.Column(
                    controls=[
                        ft.Text("地点", size=12, color=ft.Colors.GREY),
                        ft.Text(
                            loc_name,
                            size=14,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=2,
                ),
                ft.Column(
                    controls=[
                        ft.Text("时间", size=12, color=ft.Colors.GREY),
                        ft.Text(
                            ts_label,
                            size=14,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=2,
                ),
            ],
            spacing=30,
        )

        card_controls: list[ft.Control] = [badge_row, entity_row]

        # Reasoning
        if ded.reasoning:
            card_controls.append(
                ft.Column(
                    controls=[
                        ft.Text("推理过程", size=12, color=ft.Colors.GREY),
                        ft.Text(ded.reasoning, size=13),
                    ],
                    spacing=2,
                )
            )

        # Rejection reason
        if not is_accepted and ded.id in rejection_map:
            card_controls.append(
                ft.Column(
                    controls=[
                        ft.Text(
                            "拒绝原因",
                            size=12,
                            color=ft.Colors.RED,
                        ),
                        ft.Text(
                            rejection_map[ded.id],
                            size=13,
                            color=ft.Colors.RED,
                        ),
                    ],
                    spacing=2,
                )
            )

        history_items.append(
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        controls=card_controls,
                        spacing=8,
                    ),
                    padding=15,
                ),
            )
        )

    return ft.ExpansionTile(
        title=ft.Text("📜 推断历史"),
        leading=ft.Icon(ft.Icons.HISTORY),
        controls=history_items,
        expanded=False,
    )


def _show_reject_dialog(page, deduction_id, char_name, loc_name, time_slot, refresh_fn):
    """Show a dialog for rejecting a deduction with an optional reason."""
    reason_field = ft.TextField(
        label="拒绝原因（建议填写）",
        hint_text="为什么拒绝这个推断？",
        multiline=True,
        min_lines=3,
        max_lines=5,
    )

    def do_reject(e):
        reason = reason_field.value.strip() if reason_field.value else ""
        rejection = app_state.reject_deduction(deduction_id, reason)
        if rejection:
            page.snack_bar = ft.SnackBar(ft.Text("推断已拒绝"))
            page.snack_bar.open = True
        else:
            page.snack_bar = ft.SnackBar(
                ft.Text("操作失败：推断未找到"),
                bgcolor=ft.Colors.RED,
            )
            page.snack_bar.open = True
        dlg.open = False
        page.update()
        refresh_fn()

    def do_cancel(e):
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Text("拒绝推断"),
        content=ft.Column(
            controls=[
                ft.Text(f"{char_name} 在 {time_slot} 于 {loc_name}"),
                reason_field,
            ],
            tight=True,
            spacing=10,
        ),
        actions=[
            ft.TextButton("取消", on_click=do_cancel),
            ft.ElevatedButton(
                "确认拒绝",
                bgcolor=ft.Colors.RED,
                color=ft.Colors.WHITE,
                on_click=do_reject,
            ),
        ],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
