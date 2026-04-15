"""Setup tab — Consolidation DB config (left) + Source Companies grid (right)."""

import re
import fdb
from nicegui import ui, run
from config import ConsolDBConfig, EntityConfig, save_config
from shared import (CLR_PRIMARY, CLR_DANGER, AG_GRID_STYLE,
                    status_banner)


def build_setup_tab(config, on_entity_change=None):
    """Build the Setup tab UI. Returns the entity AG Grid (for tab-switch resize)."""

    ui.add_body_html(AG_GRID_STYLE)

    consol = config.consol_db

    # --- Welcome banner for first-time users ---
    welcome = ui.column().classes('w-full')
    if not consol.dcf_path:
        with welcome:
            with ui.card().classes('w-full bg-indigo-50 border border-indigo-200 p-4 mb-4'):
                ui.label('Welcome to SQL Consol Sync').classes(
                    'text-base font-bold').style(f'color: {CLR_PRIMARY}')
                ui.label('Get started in 3 steps:').classes('text-sm mt-2')
                with ui.column().classes('gap-1 ml-2 mt-1'):
                    for step, text in enumerate([
                        'Configure your consolidation database connection',
                        'Add source companies',
                        'Map customer categories in the Categories tab',
                    ], 1):
                        with ui.row().classes('items-center gap-2'):
                            ui.badge(str(step), color=CLR_PRIMARY).props('rounded')
                            ui.label(text).classes('text-sm')

    # --- Side-by-side layout (items-stretch = same height) ---
    with ui.row().classes('w-full gap-4 items-stretch'):

        # =============================================
        # LEFT CARD — Consolidation Database
        # =============================================
        with ui.card().classes('flex-1 min-w-[350px]'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Consolidation Database').classes(
                    'text-base font-bold').style(f'color: {CLR_PRIMARY}')
                with ui.row().classes('gap-2'):
                    test_btn = ui.button('Test Connection', icon='wifi_tethering',
                                         color=CLR_PRIMARY).props('outline')
                    save_btn = ui.button('Save', icon='save', color=CLR_PRIMARY)

            # -- Status banner + progress bar (right below header, visible near buttons) --
            test_result = ui.column().classes('w-full')
            test_progress = ui.linear_progress(value=0, show_value=False
                                               ).classes('w-full').props(
                f'color="{CLR_PRIMARY}" indeterminate size="4px"')
            test_progress.set_visibility(False)

            ui.separator().classes('mb-2')

            # == SQL Account Configuration (SDK) ==
            ui.label('SQL Account Configuration (SDK)').classes(
                'text-sm font-bold text-gray-600')
            ui.separator().classes('mb-2')

            with ui.column().classes('w-full gap-3'):
                with ui.column().classes('w-full gap-0'):
                    with ui.row().classes('w-full gap-0'):
                        ui.label('DCF Path').classes('text-sm font-medium')
                        ui.label(' *').classes('text-sm text-red-500')
                    dcf_path = ui.input(value=consol.dcf_path,
                                        placeholder='C:\\eStream\\SQLAccounting\\Share\\Default.DCF'
                                        ).classes('w-full').props('outlined dense')

                with ui.column().classes('w-full gap-0'):
                    with ui.row().classes('w-full gap-0'):
                        ui.label('Database Name').classes('text-sm font-medium')
                        ui.label(' *').classes('text-sm text-red-500')
                    db_name = ui.input(value=consol.db_name,
                                       placeholder='CONSOLSOA.FDB (filename only, NOT full path)'
                                       ).classes('w-full').props('outlined dense')

                with ui.column().classes('w-full gap-0'):
                    ui.label('Login Username').classes('text-sm font-medium')
                    sql_user = ui.input(value=consol.username,
                                        placeholder='ADMIN'
                                        ).classes('w-full').props('outlined dense')

                with ui.column().classes('w-full gap-0'):
                    ui.label('Login Password').classes('text-sm font-medium')
                    sql_pass = ui.input(value=consol.password,
                                        placeholder='ADMIN', password=True,
                                        password_toggle_button=True
                                        ).classes('w-full').props('outlined dense')

            # == Direct Database Connection (Read) ==
            ui.label('Direct Database Connection (Read)').classes(
                'text-sm font-bold text-gray-600 mt-4')
            ui.separator().classes('mb-2')

            with ui.column().classes('w-full gap-3'):
                with ui.column().classes('w-full gap-0'):
                    ui.label('FDB Path').classes('text-sm font-medium')
                    fb_path = ui.input(value=consol.fb_path,
                                       placeholder='C:\\eStream\\SQLAccounting\\DB\\CONSOLSOA.FDB'
                                       ).classes('w-full').props('outlined dense')

                with ui.column().classes('w-full gap-0'):
                    ui.label('Server Address').classes('text-sm font-medium')
                    fb_host = ui.input(value=consol.fb_host,
                                       placeholder='localhost'
                                       ).classes('w-full').props('outlined dense')

                with ui.column().classes('w-full gap-0'):
                    ui.label('Database Username').classes('text-sm font-medium')
                    fb_user = ui.input(value=consol.fb_user,
                                       placeholder='SYSDBA'
                                       ).classes('w-full').props('outlined dense')

                with ui.column().classes('w-full gap-0'):
                    ui.label('Database Password').classes('text-sm font-medium')
                    fb_pass = ui.input(value=consol.fb_password,
                                       placeholder='masterkey', password=True,
                                       password_toggle_button=True
                                       ).classes('w-full').props('outlined dense')

            # Shared state so _save_settings can see if the auto-test passed.
            # Both sdk_ok and fb_ok must be True before save is allowed.
            test_state = {'sdk_ok': False, 'fb_ok': False}

            async def _test_connection():
                test_state['sdk_ok'] = False
                test_state['fb_ok'] = False

                dcf = (dcf_path.value or '').strip()
                db = (db_name.value or '').strip()
                user = (sql_user.value or '').strip()
                pwd = (sql_pass.value or '').strip()

                if not dcf or not db:
                    status_banner(test_result,
                                  'Please fill in DCF Path and DB Name.', 'warning')
                    return

                test_btn.set_enabled(False)
                test_progress.set_visibility(True)

                def _test():
                    import pythoncom
                    pythoncom.CoInitialize()
                    try:
                        # Phase 1: SDK login
                        import win32com.client
                        app = win32com.client.Dispatch("SQLAcc.BizApp")
                        if app.IsLogin:
                            app.Logout()
                        app.Login(user, pwd, dcf, db)
                        if not app.IsLogin:
                            return None, None, "SDK login failed. Check username/password."
                        try:
                            ds = app.DBManager.NewDataSet(
                                "SELECT FIRST 1 COMPANYNAME FROM SY_PROFILE")
                            try:
                                company = ""
                                if ds.RecordCount > 0:
                                    company = ds.FindField("COMPANYNAME").AsString
                            finally:
                                ds.Close()
                            app.Logout()
                        except Exception as e:
                            app.Logout()
                            return None, None, f"SDK query failed: {e}"

                        # Phase 2: Firebird direct connection (if configured)
                        fb_err = None
                        fb_p = (fb_path.value or '').strip()
                        if fb_p:
                            try:
                                conn = fdb.connect(
                                    host=(fb_host.value or '').strip() or 'localhost',
                                    database=fb_p,
                                    user=(fb_user.value or '').strip() or 'SYSDBA',
                                    password=(fb_pass.value or '').strip() or 'masterkey',
                                    charset='UTF8',
                                )
                                conn.close()
                            except Exception as e:
                                fb_err = str(e)

                        return company, fb_err, None
                    except Exception as e:
                        return None, None, str(e)
                    finally:
                        pythoncom.CoUninitialize()

                company, fb_err, error = await run.io_bound(_test)

                test_progress.set_visibility(False)
                test_btn.set_enabled(True)

                if error:
                    status_banner(test_result, f'Connection failed: {error}', 'error')
                elif fb_err:
                    test_state['sdk_ok'] = True
                    msg = f'SDK connected to {db}'
                    if company:
                        msg += f' ({company})'
                    msg += f'\n\nDirect DB connection failed: {fb_err}'
                    status_banner(test_result, msg, 'warning')
                else:
                    test_state['sdk_ok'] = True
                    msg = f'Connected to {db}'
                    if company:
                        msg += f' ({company})'
                    fb_p = (fb_path.value or '').strip()
                    if fb_p:
                        test_state['fb_ok'] = True
                        msg += '\nDirect DB connection OK'
                        banner_type = 'success'
                    else:
                        msg += ('\n\nNote: Direct DB connection is not configured. '
                                'It is recommended for faster reads (categories, '
                                'preview, comparison).')
                        banner_type = 'warning'
                    status_banner(test_result, msg, banner_type)

            async def _save_settings():
                # Auto-test first — both SDK and Firebird must pass before save
                await _test_connection()
                if not (test_state['sdk_ok'] and test_state['fb_ok']):
                    ui.notify('Cannot save: connection test failed. '
                              'Fix settings and try again.', type='warning')
                    return

                config.consol_db = ConsolDBConfig(
                    dcf_path=dcf_path.value,
                    db_name=db_name.value,
                    username=sql_user.value,
                    password=sql_pass.value,
                    fb_host=fb_host.value,
                    fb_path=fb_path.value,
                    fb_user=fb_user.value,
                    fb_password=fb_pass.value,
                )
                save_config(config)
                welcome.clear()
                ui.notify('Consolidation DB settings saved.', type='positive')

            test_btn.on_click(_test_connection)
            save_btn.on_click(_save_settings)

        # =============================================
        # RIGHT CARD — Source Companies
        # =============================================
        with ui.card().classes('flex-1 min-w-[450px] flex flex-col'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Source Companies').classes(
                    'text-base font-bold').style(f'color: {CLR_PRIMARY}')
                with ui.row().classes('gap-2'):
                    refresh_btn = ui.button(
                        'Refresh', icon='refresh',
                        on_click=lambda: _refresh_sources_from_fdb(),
                        color=CLR_PRIMARY).props('outline')
                    ui.button('+ Add Company', icon='add_business',
                              on_click=lambda: _add_entity_dialog(
                                  config, grid, status_label, empty_state,
                                  on_entity_change),
                              color=CLR_PRIMARY)

            # -- Status banner + progress bar for Refresh (below header) --
            refresh_result = ui.column().classes('w-full')
            refresh_progress = ui.linear_progress(value=0, show_value=False
                                                   ).classes('w-full').props(
                f'color="{CLR_PRIMARY}" indeterminate size="4px"')
            refresh_progress.set_visibility(False)

            ui.separator().classes('mb-1')

            # -- Empty state --
            empty_state = ui.column().classes(
                'w-full items-center justify-center py-8')
            with empty_state:
                ui.icon('business', size='xl', color='grey-5')
                ui.label('No source companies added yet.').classes(
                    'text-sm text-gray-500 mt-2')
                ui.label('Click + Add Company to get started.').classes(
                    'text-xs text-gray-400')

            # -- AG Grid --
            grid = ui.aggrid({
                'columnDefs': [
                    {
                        'headerName': '#',
                        'field': 'row_num',
                        'width': 50,
                        'filter': 'agNumberColumnFilter',
                    },
                    {
                        'headerName': 'Prefix',
                        'field': 'prefix',
                        'width': 80,
                        'filter': 'agTextColumnFilter',
                        ':cellStyle': '''params => params.data && params.data._dup
                            ? {color: "#e74c3c", fontWeight: "bold",
                               backgroundColor: "#fdecea"}
                            : {color: "#5B4FC7", fontWeight: "bold"}''',
                        'tooltipField': 'prefix_tooltip',
                    },
                    {
                        'headerName': 'Company Name',
                        'field': 'name',
                        'flex': 1,
                        'filter': 'agTextColumnFilter',
                    },
                    {
                        'headerName': 'Strip',
                        'field': 'strip_prefix',
                        'width': 70,
                        'filter': 'agTextColumnFilter',
                    },
                    {
                        'headerName': 'Last Synced',
                        'field': 'last_synced',
                        'width': 145,
                        'filter': 'agTextColumnFilter',
                    },
                    {
                        'headerName': '',
                        'field': '_edit',
                        'width': 40,
                        'sortable': False,
                        'filter': False,
                        'suppressSizeToFit': True,
                        ':cellRenderer': '''params => {
                            const s = document.createElement("span");
                            s.textContent = "\\u270E";
                            s.title = "Edit";
                            s.style.cssText = "cursor:pointer;color:#5B4FC7;font-size:16px;";
                            return s;
                        }''',
                    },
                    {
                        'headerName': '',
                        'field': '_delete',
                        'width': 40,
                        'sortable': False,
                        'filter': False,
                        'suppressSizeToFit': True,
                        ':cellRenderer': '''params => {
                            const s = document.createElement("span");
                            s.textContent = "\\uD83D\\uDDD1";
                            s.title = "Delete";
                            s.style.cssText = "cursor:pointer;color:#e74c3c;font-size:16px;";
                            return s;
                        }''',
                    },
                ],
                'rowData': [],
                'animateRows': False,
                'defaultColDef': {
                    'resizable': True,
                    'sortable': True,
                    'filterParams': {'buttons': ['reset']},
                },
            }, theme='quartz', auto_size_columns=False).classes('flex-grow').style('min-height: 200px')

            # Handle edit/delete via cellClicked on icon columns
            def _on_cell_click(e):
                col = e.args.get('colId', '')
                idx = e.args.get('data', {}).get('_index')
                if idx is None or idx < 0 or idx >= len(config.entities):
                    return
                if col == '_edit':
                    _edit_entity_dialog(config, idx, grid, status_label, empty_state,
                                        on_entity_change)
                elif col == '_delete':
                    _delete_entity_dialog(config, idx, grid, status_label, empty_state,
                                          on_entity_change)

            grid.on('cellClicked', _on_cell_click)

            # Double-click any cell to edit
            grid.on('cellDoubleClicked', lambda e: (
                _edit_entity_dialog(config, e.args.get('data', {}).get('_index'),
                                    grid, status_label, empty_state,
                                    on_entity_change)
                if e.args.get('data', {}).get('_index') is not None
                and 0 <= e.args.get('data', {}).get('_index') < len(config.entities)
                else None
            ))

            status_label = ui.label('').classes('text-sm text-gray-500 mt-1')

    async def _refresh_sources_from_fdb():
        """Re-read ALIAS / company name / remark from each source DB and
        update config + grid. Lets user spot changes made in SQL Account
        (e.g. duplicate ALIASes) without opening each entity dialog."""
        if not config.entities:
            status_banner(refresh_result,
                          'No source companies to refresh.', 'warning')
            return

        refresh_btn.set_enabled(False)
        refresh_progress.set_visibility(True)
        total = len(config.entities)
        status_banner(refresh_result,
                      f'Refreshing {total} source companies from SQL Account...',
                      'success')

        def _read_all():
            results = []
            for entity in config.entities:
                try:
                    conn = fdb.connect(
                        host=entity.fb_host or 'localhost',
                        database=entity.fb_path,
                        user=entity.fb_user or 'SYSDBA',
                        password=entity.fb_password or 'masterkey',
                        charset='UTF8',
                    )
                    try:
                        cur = conn.cursor()
                        cur.execute('SELECT ALIAS, COMPANYNAME, REMARK '
                                    'FROM SY_PROFILE')
                        row = cur.fetchone()
                        cur.close()
                    finally:
                        conn.close()
                    if row:
                        results.append({
                            'prefix': (row[0] or '').strip(),
                            'name': (row[1] or '').strip(),
                            'remark': (row[2] or '').strip(),
                            'error': None,
                        })
                    else:
                        results.append({'error': 'SY_PROFILE is empty'})
                except Exception as e:
                    results.append({'error': str(e)})
            return results

        results = await run.io_bound(_read_all)

        updated = 0
        failed = 0
        for entity, result in zip(config.entities, results):
            if result.get('error'):
                failed += 1
                continue
            entity.name = result['name']
            entity.prefix = result['prefix']
            entity.remark = result['remark']
            updated += 1

        save_config(config)
        _refresh_grid(config, grid, status_label, empty_state)
        refresh_progress.set_visibility(False)
        refresh_btn.set_enabled(True)

        if on_entity_change:
            on_entity_change()

        # Detail line showing each entity's connection error (if any)
        error_lines = []
        for entity, result in zip(config.entities, results):
            if result.get('error'):
                name = entity.name or entity.prefix or entity.fb_path
                error_lines.append(f'  {name}: {result["error"]}')

        if failed:
            msg = f'Refreshed {updated} of {total} source companies. '
            msg += f'{failed} failed:\n' + '\n'.join(error_lines)
            status_banner(refresh_result, msg, 'warning')
        else:
            status_banner(refresh_result,
                          f'Refreshed {updated} source companies from SQL '
                          f'Account. Duplicate prefixes (if any) are '
                          f'highlighted in red.',
                          'success')

    # Initial data load
    _refresh_grid(config, grid, status_label, empty_state)

    return grid


def _refresh_grid(config, grid, status_label, empty_state=None):
    """Refresh grid data from config."""
    # Find duplicate prefixes (case-insensitive) for highlighting
    prefix_counts = {}
    for entity in config.entities:
        p = (entity.prefix or '').strip().lower()
        if p:
            prefix_counts[p] = prefix_counts.get(p, 0) + 1
    duplicated = {p for p, c in prefix_counts.items() if c > 1}

    row_data = []
    for i, entity in enumerate(config.entities):
        name_display = entity.name or '(not connected)'
        if entity.remark:
            name_display += f'  ({entity.remark})'
        prefix_value = entity.prefix or '-'
        prefix_key = (entity.prefix or '').strip().lower()
        is_dup = bool(prefix_key and prefix_key in duplicated)
        row_data.append({
            'row_num': i + 1,
            'prefix': prefix_value,
            'prefix_tooltip': ('Duplicate prefix — another source company has '
                               'the same ALIAS. This must be fixed before '
                               'sync.') if is_dup else prefix_value,
            'name': name_display,
            'strip_prefix': entity.customer_code_prefix or '-',
            'last_synced': entity.last_synced[:19] if entity.last_synced else 'Never',
            '_index': i,
            '_dup': is_dup,
        })

    grid.options['rowData'] = row_data
    grid.update()

    total = len(config.entities)
    status_label.set_text(f'{total} companies')

    if empty_state:
        empty_state.set_visibility(total == 0)
        grid.set_visibility(total > 0)


def _add_entity_dialog(config, grid, status_label, empty_state=None,
                       on_entity_change=None):
    """Open dialog to add a new entity."""
    _entity_dialog(config, EntityConfig(), is_new=True, index=None,
                   grid=grid, status_label=status_label, empty_state=empty_state,
                   on_entity_change=on_entity_change)


def _edit_entity_dialog(config, index, grid, status_label, empty_state=None,
                        on_entity_change=None):
    """Open dialog to edit an existing entity."""
    _entity_dialog(config, config.entities[index], is_new=False, index=index,
                   grid=grid, status_label=status_label, empty_state=empty_state,
                   on_entity_change=on_entity_change)


def _delete_entity_dialog(config, index, grid, status_label, empty_state=None,
                          on_entity_change=None):
    """Show confirm dialog, then delete a single entity."""
    entity = config.entities[index]
    name = entity.name or entity.prefix or f'Entity #{index + 1}'

    with ui.dialog() as dlg, ui.card():
        ui.label(f'Delete "{name}"?').classes('text-base font-bold')
        ui.label('This will remove the source company and its category mappings.'
                 ).classes('text-sm text-gray-600')
        with ui.row().classes('justify-end w-full mt-3 gap-2'):
            ui.button('Cancel', on_click=dlg.close).props('flat')

            def do_delete():
                config.remove_entity(index)
                save_config(config)
                _refresh_grid(config, grid, status_label, empty_state)
                dlg.close()
                ui.notify(f'Removed "{name}".', type='positive')
                if on_entity_change:
                    on_entity_change()

            ui.button('Delete', icon='delete', on_click=do_delete,
                      color=CLR_DANGER).props('outline')

    dlg.open()


def _entity_dialog(config, entity, is_new, index, grid, status_label, empty_state=None,
                   on_entity_change=None):
    """Show add/edit entity dialog."""
    title = 'Add Source Company' if is_new else 'Edit Source Company'

    with ui.dialog() as dialog, ui.card().classes('w-[600px]'):
        # Title
        with ui.row().classes('w-full justify-between items-center'):
            ui.label(title).classes('text-base font-bold').style(f'color: {CLR_PRIMARY}')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense')

        ui.separator()

        # == Direct Database Connection (Read) ==
        ui.label('Direct Database Connection (Read)').classes(
            'text-sm font-bold text-gray-600 mt-2')
        ui.separator().classes('mb-2')

        with ui.column().classes('w-full gap-3'):
            with ui.column().classes('w-full gap-0'):
                ui.label('FDB Path').classes('text-sm font-medium')
                fb_path = ui.input(value=entity.fb_path,
                                   placeholder='C:\\eStream\\SQLAccounting\\DB\\ACC-0001.FDB'
                                   ).classes('w-full').props('outlined dense')

            with ui.column().classes('w-full gap-0'):
                ui.label('Server Address').classes('text-sm font-medium')
                fb_host = ui.input(value=entity.fb_host,
                                   placeholder='localhost'
                                   ).classes('w-full').props('outlined dense')

            with ui.column().classes('w-full gap-0'):
                ui.label('Database Username').classes('text-sm font-medium')
                fb_user = ui.input(value=entity.fb_user,
                                   placeholder='SYSDBA'
                                   ).classes('w-full').props('outlined dense')

            with ui.column().classes('w-full gap-0'):
                ui.label('Database Password').classes('text-sm font-medium')
                fb_pass = ui.input(value=entity.fb_password,
                                   placeholder='masterkey', password=True,
                                   password_toggle_button=True
                                   ).classes('w-full').props('outlined dense')

        # == Company Info (auto-detected) ==
        ui.label('Company Info (auto-detected)').classes(
            'text-sm font-bold text-gray-600 mt-4')
        ui.separator().classes('mb-2')

        with ui.column().classes('w-full gap-3'):
            with ui.column().classes('w-full gap-0'):
                ui.label('Company Name').classes('text-sm font-medium')
                info_name = ui.input(value=entity.name or ''
                                     ).classes('w-full').props('outlined dense readonly')

            with ui.column().classes('w-full gap-0'):
                ui.label('Remark').classes('text-sm font-medium')
                info_remark = ui.input(value=entity.remark or ''
                                       ).classes('w-full').props('outlined dense readonly')

            with ui.column().classes('w-full gap-0'):
                ui.label('Prefix (ALIAS)').classes('text-sm font-medium')
                info_prefix = ui.input(value=entity.prefix or ''
                                       ).classes('w-full').props('outlined dense readonly')

        # == Transformer ==
        ui.label('Transformer').classes(
            'text-sm font-bold text-gray-600 mt-4')
        ui.separator().classes('mb-2')

        with ui.column().classes('w-full gap-0'):
            ui.label('Code Prefix to Remove').classes('text-sm font-medium')
            strip_prefix = ui.input(value=entity.customer_code_prefix,
                                    placeholder='e.g. 300-'
                                    ).classes('w-full').props('outlined dense')
            ui.label('If customer codes start with "300-", enter "300-" here.'
                     ).classes('text-xs text-gray-400')

        # -- Test result + progress --
        entity_test_result = ui.column().classes('w-full mt-2')
        entity_test_progress = ui.linear_progress(value=0, show_value=False
                                                   ).classes('w-full').props(
            f'color="{CLR_PRIMARY}" indeterminate size="4px"')
        entity_test_progress.set_visibility(False)

        # --- Buttons ---
        ui.separator().classes('mt-3')
        with ui.row().classes('justify-end mt-2 w-full gap-2'):
            ui.button('Cancel', on_click=dialog.close).props('flat')

            entity_test_btn = ui.button('Test Connection', icon='wifi_tethering',
                                        color=CLR_PRIMARY).props('outline')

            # Staged test results — NOT written to `entity` until save succeeds.
            # Otherwise a blocked/cancelled save would leave the in-memory entity
            # mutated and out of sync with config.json and the main grid.
            entity_test_state = {'ok': False, 'name': '', 'remark': '', 'prefix': ''}

            async def on_test():
                entity_test_state['ok'] = False
                entity_test_state['name'] = ''
                entity_test_state['remark'] = ''
                entity_test_state['prefix'] = ''
                entity_test_btn.set_enabled(False)
                entity_test_progress.set_visibility(True)

                def _test():
                    try:
                        conn = fdb.connect(
                            host=fb_host.value,
                            database=fb_path.value,
                            user=fb_user.value,
                            password=fb_pass.value,
                            charset='UTF8',
                        )
                        cur = conn.cursor()
                        cur.execute('SELECT ALIAS, COMPANYNAME, REMARK FROM SY_PROFILE')
                        profile = cur.fetchone()

                        sample_code = ''
                        detected_prefix = ''
                        try:
                            cur.execute('SELECT FIRST 1 CODE FROM AR_CUSTOMER ORDER BY CODE')
                            row = cur.fetchone()
                            if row:
                                sample_code = (row[0] or '').strip()
                                m = re.match(r'^([A-Za-z0-9]+[-/.])(.+)$', sample_code)
                                if m:
                                    detected_prefix = m.group(1)
                        except Exception:
                            pass

                        cur.close()
                        conn.close()
                        return profile, sample_code, detected_prefix, None
                    except Exception as e:
                        return None, '', '', str(e)

                profile, sample_code, detected_prefix, error = await run.io_bound(_test)

                entity_test_progress.set_visibility(False)
                entity_test_btn.set_enabled(True)

                if error:
                    status_banner(entity_test_result, f'Connection failed: {error}', 'error')
                    return

                if profile:
                    alias = (profile[0] or '').strip()
                    company = (profile[1] or '').strip()
                    remark = (profile[2] or '').strip()
                    # Update read-only info fields for visual feedback only
                    info_name.set_value(company)
                    info_remark.set_value(remark)
                    info_prefix.set_value(alias)
                    # Stage values — do NOT mutate `entity` yet; that happens on save
                    entity_test_state['name'] = company
                    entity_test_state['remark'] = remark
                    entity_test_state['prefix'] = alias

                    if detected_prefix and strip_prefix.value in ('', '300-'):
                        strip_prefix.set_value(detected_prefix)

                    if alias:
                        entity_test_state['ok'] = True

                    msg = f'Connected! {company} (Alias: {alias})'
                    if sample_code:
                        msg += f' | Sample: {sample_code}'
                    status_banner(entity_test_result, msg, 'success')
                else:
                    status_banner(entity_test_result,
                                  'Connected but SY_PROFILE is empty.', 'warning')

            entity_test_btn.on_click(on_test)

            async def on_save():
                path = (fb_path.value or '').strip()
                if not path:
                    ui.notify('FDB Path is required.', type='warning')
                    return

                # Fast check — duplicate FDB path (no test round-trip needed)
                for i, existing in enumerate(config.entities):
                    if i == index:
                        continue  # skip self when editing
                    if existing.fb_path and existing.fb_path.strip().lower() == path.lower():
                        name = existing.name or existing.prefix or f'Entity #{i + 1}'
                        ui.notify(f'This database is already added as "{name}".',
                                  type='warning')
                        return

                # Auto-test — stages new name/remark/prefix in entity_test_state
                await on_test()
                if not entity_test_state['ok']:
                    ui.notify('Cannot save: connection test failed. '
                              'Fix settings and try again.', type='warning')
                    return

                # Duplicate prefix (ALIAS) check — prefix must be unique because
                # it disambiguates document numbers in the consol DB.
                # Case-insensitive (s1 and S1 are duplicates). Uses the FRESH
                # alias from entity_test_state, not the stored entity.prefix.
                new_prefix = (entity_test_state['prefix'] or '').strip()
                if new_prefix:
                    for i, existing in enumerate(config.entities):
                        if i == index:
                            continue
                        existing_prefix = (existing.prefix or '').strip()
                        if existing_prefix and existing_prefix.lower() == new_prefix.lower():
                            name = existing.name or existing.prefix or f'Entity #{i + 1}'
                            status_banner(entity_test_result,
                                          f'Duplicate prefix "{new_prefix}" — '
                                          f'already used by "{name}". Prefixes must '
                                          f'be unique because they disambiguate '
                                          f'document numbers in the consolidation DB.',
                                          'error')
                            return

                # All checks passed — now commit staged values to the entity object
                entity.name = entity_test_state['name']
                entity.remark = entity_test_state['remark']
                entity.prefix = entity_test_state['prefix']
                entity.fb_path = fb_path.value
                entity.fb_host = fb_host.value
                entity.fb_user = fb_user.value
                entity.fb_password = fb_pass.value
                entity.customer_code_prefix = strip_prefix.value

                if is_new:
                    config.add_entity(entity)
                else:
                    config.entities[index] = entity

                save_config(config)
                _refresh_grid(config, grid, status_label, empty_state)
                dialog.close()
                ui.notify('Company saved.', type='positive')
                if on_entity_change:
                    on_entity_change()

            ui.button('Save', icon='save', on_click=on_save, color=CLR_PRIMARY)

    dialog.open()
