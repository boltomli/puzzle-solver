# Library — Puzzle Solver QoL Mission

## NiceGUI Patterns Used in This Project

### Combo Select (dropdown + manual input)
```python
ui.select(options=['opt1', 'opt2'], new_value_mode='add', label='Model').classes('w-full')
# Or with use-input prop for filtering:
ui.select(options=['opt1'], label='Model').props('use-input new-value-mode=add')
```

### Banner for notifications
```python
with ui.card().classes('w-full q-pa-sm q-mb-md').style('border: 1px solid #ff9800; background-color: rgba(255, 152, 0, 0.08);'):
    with ui.row().classes('items-center gap-2'):
        ui.icon('warning', color='warning')
        ui.label('API 未配置，请前往设置页面配置').classes('text-body2')
        ui.button('前往设置', on_click=lambda: tabs.set_value('settings')).props('flat dense color=warning')
```

### Tab with badge
```python
with ui.tabs() as tabs:
    ui.tab('review', label='审查', icon='fact_check')
# Badge can be added via:
# Use ui.badge() positioned near the tab, or use JavaScript/Quasar slots
```

### PyInstaller frozen state handling
```python
import sys
import os
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)
```

### OpenAI SDK list models
```python
async def list_models(self) -> list[str]:
    self._ensure_client()
    assert self.client is not None
    models = await self.client.models.list()
    return sorted([m.id for m in models.data])
```
