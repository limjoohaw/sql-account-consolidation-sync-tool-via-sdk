"""Shared theme constants and utilities for NiceGUI UI."""

from nicegui import ui

# Brand colors (SQL Account indigo-purple palette)
CLR_PRIMARY = "#5B4FC7"
CLR_SECONDARY = "#7B6FD4"
CLR_ACCENT = "#8B7FE8"
CLR_BG_SEC = "#E8E4F8"
CLR_BG_HOVER = "#D5CFEF"
CLR_DANGER = "#e74c3c"
CLR_DANGER_HOVER = "#c0392b"

# Global font — JetBrains Mono via Google Fonts, Consolas fallback for offline
FONT_IMPORT = '''
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
body, .q-field__native, .q-field__input, .q-btn, .q-tab__label,
.q-radio__label, .q-checkbox__label, .q-card, .q-banner,
.q-field__label, .q-item__label, .q-select__dropdown,
.q-menu, .q-notification, .q-dialog {
    font-family: "JetBrains Mono", Consolas, monospace !important;
    font-size: 13px;
}
/* Force Quasar inputs to fill parent width, never exceed */
.q-field { width: 100% !important; min-width: 0 !important; overflow: hidden !important; }
/* Multi-select chips: one per line, fixed width, no overflow */
.q-select .q-field__native {
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 2px !important;
    overflow-y: auto !important;
    max-height: 150px !important;
    min-width: 0 !important;
}
.q-select .q-field__native .q-chip {
    width: 49% !important;
    max-width: 49% !important;
    min-width: 0 !important;
    margin: 0 !important;
    flex-shrink: 0 !important;
}
.q-select .q-field__native .q-chip .q-chip__content {
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    min-width: 0 !important;
}
</style>
'''

# AG Grid custom CSS — targets the nicegui-aggrid wrapper (AG Grid v34 uses JS themes, not CSS classes)
AG_GRID_STYLE = """
<style>
.nicegui-aggrid {
    --ag-header-background-color: #E8E4F8;
    --ag-odd-row-background-color: #F3F0FA;
    --ag-selected-row-background-color: #D5CFEF;
    --ag-range-selection-background-color: #D5CFEF80;
    --ag-font-family: "JetBrains Mono", Consolas, monospace;
    --ag-font-size: 13px;
}
.nicegui-aggrid .ag-header-cell-text {
    font-weight: bold;
    font-family: Arial, sans-serif;
}
</style>
"""


async def _set_checked_filtered(grid, field: str, value: bool):
    """Tick/un-tick all visible (filtered) rows in an AG Grid."""
    js_value = 'true' if value else 'false'
    await ui.run_javascript(f'''
        const grid = getElement({grid.id});
        grid.api.forEachNodeAfterFilter(node => {{
            node.setDataValue('{field}', {js_value});
        }});
    ''')
    action = 'Ticked' if value else 'Un-ticked'
    ui.notify(f'{action} all visible rows.', type='info')


def status_banner(container, message: str, banner_type: str = 'success'):
    """Show a persistent colored status banner inside a container.

    Args:
        container: NiceGUI container element (e.g. ui.column) to render into
        message: Text to display
        banner_type: 'success' (green), 'error' (red), or 'warning' (yellow)
    """
    container.clear()
    styles = {
        'success': ('bg-green-50 border-green-500 text-green-800', 'check_circle', 'green'),
        'error': ('bg-red-50 border-red-500 text-red-800', 'error', 'red'),
        'warning': ('bg-yellow-50 border-yellow-500 text-yellow-800', 'warning', 'orange'),
    }
    css, icon_name, icon_color = styles.get(banner_type, styles['success'])
    with container:
        with ui.card().classes(f'w-full border-l-4 p-3 {css}').props('flat'):
            with ui.row().classes('items-center gap-2'):
                ui.icon(icon_name, color=icon_color, size='sm')
                ui.label(message).classes('text-sm')
