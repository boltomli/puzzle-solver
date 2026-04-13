# Library — Puzzle Solver Flet Rewrite

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
# After any app_state mutation, rebuild the affected content:
def refresh():
    content_container.content = build_content()
    page.update()

# Example:
def on_add_character(e):
    app_state.add_character(name=name_field.value)
    page.snack_bar = ft.SnackBar(ft.Text("角色已添加"))
    page.snack_bar.open = True
    refresh()
```

### Async Operations
```python
async def run_analysis(e):
    progress = ft.ProgressRing()
    content.controls.append(progress)
    page.update()
    try:
        result = await service.analyze_script(proj, script)
        # handle result
    finally:
        content.controls.remove(progress)
        page.update()
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

### OpenAI SDK — List Models (unchanged)
```python
async def list_models(self) -> list[str]:
    self._ensure_client()
    assert self.client is not None
    models = await self.client.models.list()
    return sorted([m.id for m in models.data])
```

## Pure Logic Functions (MUST PRESERVE)

### build_matrix_data (matrix.py)
Tested by test_matrix.py — 11 tests. Must have identical signature:
`def build_matrix_data(project: Project) -> list[dict]`

### _create_single_deduction (scripts.py)
Tested by test_scripts.py. Must have identical signature:
`def _create_single_deduction(proj, fact_dict: dict, script_id: str) -> bool`

### _create_deductions_from_facts (scripts.py)
Tested by test_scripts.py. Must have identical signature:
`def _create_deductions_from_facts(proj, direct_facts: list[dict], script_id: str) -> int`

### _is_api_configured (scripts.py)
Tested by test_scripts.py. Must have identical signature:
`def _is_api_configured() -> bool`
