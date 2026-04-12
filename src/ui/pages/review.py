"""推断审查页面 — Review tab.

Displays pending deductions for user to accept, reject, or skip.
Sorted by confidence: certain → high → medium → low.
"""

from nicegui import ui

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
    ConfidenceLevel.certain: "positive",
    ConfidenceLevel.high: "primary",
    ConfidenceLevel.medium: "warning",
    ConfidenceLevel.low: "grey",
}


def review_tab_content():
    """Render the deduction review tab content."""
    with ui.column().classes("w-full q-pa-md gap-4"):
        ui.label("推断审查").classes("text-h5")

        if not app_state.current_project:
            ui.label("请先选择或创建一个项目").classes("text-body1 text-grey")
            return

        @ui.refreshable
        def review_content():
            proj = app_state.current_project
            if not proj:
                return

            pending = [
                d for d in proj.deductions if d.status == DeductionStatus.pending
            ]

            if not pending:
                with ui.card().classes("w-full q-pa-lg text-center"):
                    ui.icon("check_circle", size="3em", color="positive")
                    ui.label("暂无待审查的推断").classes(
                        "text-body1 text-grey q-mt-sm"
                    )
                    ui.label("可在「矩阵」页面触发 AI 推断或消元推断").classes(
                        "text-caption text-grey"
                    )
                return

            # Sort by confidence
            pending.sort(key=lambda d: _CONFIDENCE_ORDER.get(d.confidence, 99))

            ui.label(f"共 {len(pending)} 条待审查推断").classes("text-subtitle1")

            # Batch actions
            with ui.row().classes("gap-2"):

                def clear_all():
                    count = app_state.clear_pending_deductions()
                    ui.notify(f"已清除 {count} 条待审查推断", type="info")
                    review_content.refresh()

                ui.button("清除所有待审查", on_click=clear_all, icon="clear_all").props(
                    "flat color=negative"
                )

            # Build lookup maps
            char_map = {c.id: c.name for c in proj.characters}
            loc_map = {l.id: l.name for l in proj.locations}

            for ded in pending:
                char_name = char_map.get(ded.character_id, ded.character_id[:8])
                loc_name = loc_map.get(ded.location_id, ded.location_id[:8])
                conf_label = _CONFIDENCE_LABELS.get(ded.confidence, str(ded.confidence))
                conf_color = _CONFIDENCE_COLORS.get(ded.confidence, "grey")

                with ui.card().classes("w-full q-mb-md"):
                    with ui.card_section():
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("lightbulb", color="amber")
                            ui.label("推断").classes("text-h6")
                            ui.badge(
                                f"置信度: {conf_label}",
                                color=conf_color,
                            ).classes("text-body2")

                    with ui.card_section():
                        with ui.row().classes("gap-6 flex-wrap"):
                            with ui.column().classes("gap-1"):
                                ui.label("人物").classes("text-caption text-grey")
                                ui.label(char_name).classes(
                                    "text-subtitle1 text-weight-bold"
                                )
                            with ui.column().classes("gap-1"):
                                ui.label("地点").classes("text-caption text-grey")
                                ui.label(loc_name).classes(
                                    "text-subtitle1 text-weight-bold"
                                )
                            with ui.column().classes("gap-1"):
                                ui.label("时间").classes("text-caption text-grey")
                                ui.label(ded.time_slot).classes(
                                    "text-subtitle1 text-weight-bold"
                                )

                    if ded.reasoning:
                        with ui.card_section():
                            ui.label("推理过程").classes(
                                "text-caption text-grey q-mb-xs"
                            )
                            ui.label(ded.reasoning).classes("text-body2")

                    with ui.card_actions().classes("justify-end"):

                        def make_accept_handler(d_id):
                            def handler():
                                fact = app_state.accept_deduction(d_id)
                                if fact:
                                    ui.notify("推断已接受，已创建事实", type="positive")
                                    # Auto-cascade: run elimination after acceptance
                                    try:
                                        new_deds = DeductionService.run_cascade(proj)
                                        count = 0
                                        for ded in new_deds:
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
                                                f"已接受推断。消元推断发现 {count} 条新确定推断",
                                                type="positive",
                                            )
                                        else:
                                            ui.notify(
                                                "已接受推断。消元推断未发现新推断",
                                                type="info",
                                            )
                                    except Exception:
                                        pass  # Don't block acceptance on cascade failure
                                review_content.refresh()

                            return handler

                        def make_reject_handler(d_id, d_char, d_loc, d_ts):
                            def handler():
                                _show_reject_dialog(
                                    d_id, d_char, d_loc, d_ts, review_content
                                )

                            return handler

                        ui.button(
                            "✅ 接受",
                            on_click=make_accept_handler(ded.id),
                        ).props("color=positive")
                        ui.button(
                            "❌ 拒绝",
                            on_click=make_reject_handler(
                                ded.id, char_name, loc_name, ded.time_slot
                            ),
                        ).props("color=negative outline")

        review_content()

        # --- Deduction History Section ---
        _render_deduction_history()


def _render_deduction_history():
    """Render the history of resolved (accepted/rejected) deductions."""
    proj = app_state.current_project
    if not proj:
        return

    resolved = [
        d for d in proj.deductions
        if d.status in (DeductionStatus.accepted, DeductionStatus.rejected)
    ]

    if not resolved:
        return

    # Sort by resolved_at descending (most recent first)
    resolved.sort(key=lambda d: d.resolved_at or d.created_at, reverse=True)

    # Build lookup maps
    char_map = {c.id: c.name for c in proj.characters}
    loc_map = {l.id: l.name for l in proj.locations}

    # Build rejection reason map
    rejection_map = {}
    for r in proj.rejections:
        if r.from_deduction_id:
            rejection_map[r.from_deduction_id] = r.reason

    with ui.expansion("📜 推断历史", icon="history").classes("w-full"):
        ui.label(f"共 {len(resolved)} 条已处理推断").classes("text-subtitle2 q-mb-sm")

        for ded in resolved:
            char_name = char_map.get(ded.character_id, ded.character_id[:8])
            loc_name = loc_map.get(ded.location_id, ded.location_id[:8])
            conf_label = _CONFIDENCE_LABELS.get(ded.confidence, str(ded.confidence))

            is_accepted = ded.status == DeductionStatus.accepted
            status_label = "已接受" if is_accepted else "已拒绝"
            status_color = "positive" if is_accepted else "negative"
            status_icon = "check_circle" if is_accepted else "cancel"

            with ui.card().classes("w-full q-mb-sm"):
                with ui.card_section():
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(status_icon, color=status_color)
                        ui.badge(status_label, color=status_color).classes("text-body2")
                        ui.badge(
                            f"置信度: {conf_label}",
                            color=_CONFIDENCE_COLORS.get(ded.confidence, "grey"),
                        ).classes("text-body2")
                        if ded.resolved_at:
                            ui.label(
                                ded.resolved_at.strftime("%m-%d %H:%M")
                            ).classes("text-caption text-grey")

                with ui.card_section():
                    with ui.row().classes("gap-6 flex-wrap"):
                        with ui.column().classes("gap-1"):
                            ui.label("人物").classes("text-caption text-grey")
                            ui.label(char_name).classes("text-subtitle1 text-weight-bold")
                        with ui.column().classes("gap-1"):
                            ui.label("地点").classes("text-caption text-grey")
                            ui.label(loc_name).classes("text-subtitle1 text-weight-bold")
                        with ui.column().classes("gap-1"):
                            ui.label("时间").classes("text-caption text-grey")
                            ui.label(ded.time_slot).classes("text-subtitle1 text-weight-bold")

                if ded.reasoning:
                    with ui.card_section():
                        ui.label("推理过程").classes("text-caption text-grey q-mb-xs")
                        ui.label(ded.reasoning).classes("text-body2")

                # Show rejection reason if rejected
                if not is_accepted and ded.id in rejection_map:
                    with ui.card_section():
                        ui.label("拒绝原因").classes("text-caption text-negative q-mb-xs")
                        ui.label(rejection_map[ded.id]).classes("text-body2 text-negative")


def _show_reject_dialog(
    deduction_id: str,
    char_name: str,
    loc_name: str,
    time_slot: str,
    refresh_fn,
):
    """Show a dialog for rejecting a deduction with an optional reason."""
    with ui.dialog() as dlg, ui.card().classes("w-96"):
        ui.label("拒绝推断").classes("text-h6 q-mb-md")
        ui.label(f"{char_name} 在 {time_slot} 于 {loc_name}").classes("text-body1")

        reason_input = ui.textarea(
            label="拒绝原因（建议填写）",
            placeholder="为什么拒绝这个推断？",
        ).classes("w-full").props("rows=3")

        def do_reject():
            reason = reason_input.value.strip()
            rejection = app_state.reject_deduction(deduction_id, reason)
            if rejection:
                ui.notify("推断已拒绝", type="info")
            dlg.close()
            refresh_fn.refresh()

        with ui.row().classes("w-full justify-end q-mt-md"):
            ui.button("取消", on_click=dlg.close).props("flat")
            ui.button("确认拒绝", on_click=do_reject).props("color=negative")

    dlg.open()
