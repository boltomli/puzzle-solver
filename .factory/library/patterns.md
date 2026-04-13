# Library — Puzzle Solver Matrix Enhancement

## Flet Patterns for This Project

### Page Tab Structure
```python
import flet as ft

def main(page: ft.Page):
    page.title = "Puzzle Solver"
    page.theme_mode = ft.ThemeMode.DARK

    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(text="剧本", icon=ft.Icons.DESCRIPTION),
            ft.Tab(text="矩阵", icon=ft.Icons.GRID_ON),
            ft.Tab(text="管理", icon=ft.Icons.PEOPLE),
            ft.Tab(text="审查", icon=ft.Icons.FACT_CHECK),
            ft.Tab(text="设置", icon=ft.Icons.SETTINGS),
        ],
    )
```

### Dialog Pattern
```python
def show_confirm_dialog(page, title, message, on_confirm):
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[
            ft.TextButton("取消", on_click=lambda e: close_dlg()),
            ft.ElevatedButton("确认", on_click=lambda e: (on_confirm(), close_dlg())),
        ],
    )
    def close_dlg():
        dlg.open = False
        page.update()
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
```

### State Refresh Pattern
```python
def refresh():
    content_container.content = build_content()
    page.update()

def on_add_character(e):
    app_state.add_character(name=name_field.value)
    page.snack_bar = ft.SnackBar(ft.Text("角色已添加"))
    page.snack_bar.open = True
    refresh()
```

### Color-Coded Cells in DataTable
```python
def make_cell(value, status):
    color_map = {
        "confirmed": ft.Colors.GREEN_100,
        "pending": ft.Colors.AMBER_100,
        "unknown": None,
    }
    bg = color_map.get(status)
    return ft.DataCell(
        ft.Container(
            content=ft.Text(value or "—", color=ft.Colors.GREY if not value else None),
            bgcolor=bg,
            padding=5,
            border_radius=4,
        )
    )
```

### Chip Multi-Select Pattern
```python
def build_chip_selector(items, on_change):
    """Build a row of selectable chips for multi-select."""
    selected_ids = set()

    def make_select_handler(item_id):
        def handler(e):
            if e.control.selected:
                selected_ids.add(item_id)
            else:
                selected_ids.discard(item_id)
            on_change(selected_ids)
        return handler

    return ft.Row(
        controls=[
            ft.Chip(
                label=ft.Text(item.name),
                selected=False,
                on_select=make_select_handler(item.id),
            )
            for item in items
        ],
        wrap=True,
    )
```

## Pure Logic Functions (MUST PRESERVE)

### build_matrix_data (matrix.py)
Tested by test_matrix.py — 11 tests. Must have identical signature:
`def build_matrix_data(project: Project) -> list[dict]`

### build_location_time_data (matrix.py) — NEW
Same pattern but rows=locations, cells=character names.
`def build_location_time_data(project: Project) -> list[dict]`

### _create_single_deduction (scripts.py)
Tested by test_scripts.py. Must have identical signature:
`def _create_single_deduction(proj, fact_dict: dict, script_id: str) -> bool`

### _create_deductions_from_facts (scripts.py)
Tested by test_scripts.py. Must have identical signature:
`def _create_deductions_from_facts(proj, direct_facts: list[dict], script_id: str) -> int`

### _is_api_configured (scripts.py)
Tested by test_scripts.py. Must have identical signature:
`def _is_api_configured() -> bool`

## Deduction Index Pattern

```python
# In AppState.__init__:
self._fact_index: set[tuple[str, str, str]] = set()
self._pending_index: set[tuple[str, str, str]] = set()
self._rejection_index: set[tuple[str, str, str]] = set()

# Rebuild from project data:
def _rebuild_indexes(self):
    proj = self.current_project
    if not proj:
        self._fact_index = set()
        self._pending_index = set()
        self._rejection_index = set()
        return
    self._fact_index = {(f.character_id, f.location_id, f.time_slot) for f in proj.facts}
    self._pending_index = {
        (d.character_id, d.location_id, d.time_slot)
        for d in proj.deductions if d.status == DeductionStatus.pending
    }
    self._rejection_index = {(r.character_id, r.location_id, r.time_slot) for r in proj.rejections}

# In add_deduction:
def add_deduction(self, deduction) -> bool:
    key = (deduction.character_id, deduction.location_id, deduction.time_slot)
    if key in self._fact_index or key in self._pending_index or key in self._rejection_index:
        return False
    self.current_project.deductions.append(deduction)
    self._pending_index.add(key)
    self.save()
    return True
```
