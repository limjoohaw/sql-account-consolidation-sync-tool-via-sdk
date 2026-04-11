"""NiceGUI-based UI for SQL Account Consolidation Sync Tool."""

import os
import sys
import asyncio
import fdb
from nicegui import ui
from config import load_config
from version import APP_NAME, APP_VERSION, APP_BUILD_NUMBER
from shared import CLR_PRIMARY, CLR_SECONDARY, CLR_ACCENT, CLR_BG_SEC, FONT_IMPORT


def _get_company_categories(cfg):
    """Fetch Company Categories from consol DB via Firebird."""
    consol = cfg.consol_db
    if not consol.fb_path:
        if consol.dcf_path and consol.db_name:
            from consol_writer import fetch_company_categories
            return fetch_company_categories(consol)
        return []

    conn = None
    try:
        conn = fdb.connect(
            host=consol.fb_host,
            database=consol.fb_path,
            user=consol.fb_user,
            password=consol.fb_password,
            charset='UTF8',
        )
        cur = conn.cursor()
        cur.execute('SELECT CODE, DESCRIPTION FROM COMPANYCATEGORY '
                    'WHERE ISACTIVE=TRUE ORDER BY CODE')
        categories = []
        for row in cur.fetchall():
            code = (row[0] or '').strip()
            desc = (row[1] or '').strip()
            if code:
                categories.append({'code': code, 'description': desc})
        cur.close()
        return categories
    except Exception as e:
        ui.notify(f'Could not read categories: {e}', type='negative', multi_line=True)
        return []
    finally:
        if conn:
            conn.close()


def _show_about():
    ui.notify(
        f'{APP_NAME}\n'
        f'Version: {APP_VERSION} (Build {APP_BUILD_NUMBER})\n\n'
        f'SQL Account Consolidation Sync Tool\n'
        f'Powered by SQL Account SDK',
        type='info', multi_line=True,
    )


def _show_whats_new():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        changelog_path = os.path.join(base, '_internal', 'CHANGELOG.md')
        if not os.path.exists(changelog_path):
            changelog_path = os.path.join(base, 'CHANGELOG.md')
    else:
        changelog_path = os.path.join(os.path.dirname(__file__), 'CHANGELOG.md')

    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        content = 'No changelog available.'

    with ui.dialog() as dlg, ui.card().classes('w-[520px] max-h-[80vh]'):
        ui.label(f"What's New \u2014 {APP_NAME}").classes('text-lg font-bold'
                 ).style(f'color: {CLR_PRIMARY}')
        ui.markdown(content).classes('overflow-auto')
        ui.button('Close', on_click=dlg.close, color=CLR_PRIMARY)
    dlg.open()


def create_app():
    """Register the NiceGUI page handler.

    Uses @ui.page('/') instead of auto-index mode because PyInstaller bundles
    can't use auto-index — NiceGUI's auto-index calls runpy.run_path(sys.argv[0])
    on every request, but in a frozen exe sys.argv[0] is the binary itself,
    causing 'source code string cannot contain null bytes' errors.
    """

    @ui.page('/')
    def _index():
        config = load_config()

        # --- Theme & Font ---
        ui.colors(primary=CLR_PRIMARY, secondary=CLR_SECONDARY, accent=CLR_ACCENT)
        ui.add_body_html(FONT_IMPORT)

        # --- Header ---
        with ui.header().classes('items-center justify-between px-4 py-2'
                                 ).style(f'background-color: {CLR_PRIMARY}'):
            ui.label(f'{APP_NAME} v{APP_VERSION}').classes(
                'text-white text-lg font-bold')
            with ui.row().classes('gap-2'):
                ui.button("What's New", on_click=_show_whats_new
                          ).props('flat text-color="white" dense')
                ui.button('About', on_click=_show_about
                          ).props('flat text-color="white" dense')

        # --- Tabs (3 tabs: Setup | Categories | Sync) ---
        with ui.tabs().classes('w-full').style(
                f'background-color: {CLR_BG_SEC}') as tabs:
            setup_tab = ui.tab('Setup', icon='settings')
            cat_tab = ui.tab('Categories', icon='category')
            sync_tab = ui.tab('Sync', icon='sync')

        # Smart default: Setup for first-time users, Sync for returning users
        default_tab = setup_tab if not config.consol_db.dcf_path else sync_tab

        # Mutable list for cross-tab entity change callbacks (setup tab is
        # built before category/sync tabs, so callbacks are registered after).
        _entity_change_cbs = []

        def _on_entity_change():
            for cb in _entity_change_cbs:
                cb()

        # --- Tab Panels ---
        with ui.tab_panels(tabs, value=default_tab).classes('w-full flex-grow'):

            with ui.tab_panel(setup_tab).classes('p-4'):
                from tab_setup import build_setup_tab
                setup_grid = build_setup_tab(config,
                                             on_entity_change=_on_entity_change)

            with ui.tab_panel(cat_tab).classes('p-4'):
                from tab_category import build_category_tab
                cat_grid, cat_state = build_category_tab(config, _get_company_categories)

            with ui.tab_panel(sync_tab).classes('p-4'):
                from tab_sync import build_sync_tab
                sync_state = build_sync_tab(config)

        # Register entity-change refresh callbacks now that all tabs are built
        _entity_change_cbs.append(cat_state['refresh_entities'])
        _entity_change_cbs.append(sync_state['refresh_entities'])

        # AG Grid doesn't size correctly when initialized in a hidden tab.
        # Wait for Quasar tab transition, then resize via JS (avoid grid.update()
        # which re-serializes internal state and causes circular reference errors).
        # Map tabs to their grids for targeted resize
        tab_grids = {}
        if setup_grid:
            tab_grids[setup_tab] = [setup_grid]
        tab_grids[cat_tab] = [cat_grid]

        async def _on_tab_change(e):
            await asyncio.sleep(0.3)
            # Refresh entity dropdowns when switching to Categories or Sync tab
            if e.value == cat_tab and cat_state.get('refresh_entities'):
                cat_state['refresh_entities']()
            elif e.value == sync_tab and sync_state and sync_state.get('refresh_entities'):
                sync_state['refresh_entities']()
            # Resize AG Grids in active tab
            active_grids = tab_grids.get(e.value, [])
            for g in active_grids:
                try:
                    await g.run_grid_method('sizeColumnsToFit')
                except Exception:
                    pass

        tabs.on_value_change(_on_tab_change)

        # --- Footer ---
        with ui.footer().classes('py-1 px-4').style(f'background-color: {CLR_BG_SEC}'):
            ui.label(f'{APP_NAME} v{APP_VERSION} ({APP_BUILD_NUMBER})'
                     ).classes('text-xs text-gray-500')
