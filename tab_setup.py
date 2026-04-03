"""Setup tab — Consolidation DB config (left) + Source Companies grid (right)."""

import re
import fdb
from nicegui import ui, run
from config import ConsolDBConfig, EntityConfig, save_config
from shared import (CLR_PRIMARY, CLR_DANGER, AG_GRID_STYLE,
                    status_banner)


def build_setup_tab(config):
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

            # -- Test result banner area --
            test_result = ui.column().classes('w-full mt-2')

            # -- Progress bar for test connection (hidden by default) --
            test_progress = ui.linear_progress(value=0, show_value=False
                                               ).classes('w-full').props(
                f'color="{CLR_PRIMARY}" indeterminate size="4px"')
            test_progress.set_visibility(False)

            async def _test_connection():
                dcf = (dcf_path.value or '').strip()
                db = (db_name.value or '').strip()
                user = (sql_user.value or '').strip()
                pwd = (sql_pass.value or '').strip()

                if not dcf or not db:
                    ui.notify('Please fill in DCF Path and DB Name.', type='warning')
                    return

                test_btn.set_enabled(False)
                test_progress.set_visibility(True)

                def _test():
                    import pythoncom
                    pythoncom.CoInitialize()
                    try:
                        import win32com.client
                        app = win32com.client.Dispatch("SQLAcc.BizApp")
                        if app.IsLogin:
                            app.Logout()
                        app.Login(user, pwd, dcf, db)
                        if not app.IsLogin:
                            return None, "Login failed. Please check your username/password."
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
                            return company, None
                        except Exception as e:
                            app.Logout()
                            return None, str(e)
                    except Exception as e:
                        return None, str(e)
                    finally:
                        pythoncom.CoUninitialize()

                company, error = await run.io_bound(_test)

                test_progress.set_visibility(False)
                test_btn.set_enabled(True)

                if error:
                    status_banner(test_result, f'Connection failed: {error}', 'error')
                else:
                    msg = f'Connected to {db}'
                    if company:
                        msg += f' ({company})'
                    status_banner(test_result, msg, 'success')

            def _save_settings():
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
                ui.button('+ Add Company', icon='add_business',
                          on_click=lambda: _add_entity_dialog(
                              config, grid, status_label, empty_state),
                          color=CLR_PRIMARY)

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
                        'cellStyle': {'color': CLR_PRIMARY, 'fontWeight': 'bold'},
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
                    _edit_entity_dialog(config, idx, grid, status_label, empty_state)
                elif col == '_delete':
                    _delete_entity_dialog(config, idx, grid, status_label, empty_state)

            grid.on('cellClicked', _on_cell_click)

            # Double-click any cell to edit
            grid.on('cellDoubleClicked', lambda e: (
                _edit_entity_dialog(config, e.args.get('data', {}).get('_index'),
                                    grid, status_label, empty_state)
                if e.args.get('data', {}).get('_index') is not None
                and 0 <= e.args.get('data', {}).get('_index') < len(config.entities)
                else None
            ))

            status_label = ui.label('').classes('text-sm text-gray-500 mt-1')

    # Initial data load
    _refresh_grid(config, grid, status_label, empty_state)

    return grid


def _refresh_grid(config, grid, status_label, empty_state=None):
    """Refresh grid data from config."""
    row_data = []
    for i, entity in enumerate(config.entities):
        name_display = entity.name or '(not connected)'
        if entity.remark:
            name_display += f'  ({entity.remark})'
        row_data.append({
            'row_num': i + 1,
            'prefix': entity.prefix or '-',
            'name': name_display,
            'strip_prefix': entity.customer_code_prefix or '-',
            'last_synced': entity.last_synced[:19] if entity.last_synced else 'Never',
            '_index': i,
        })

    grid.options['rowData'] = row_data
    grid.update()

    total = len(config.entities)
    status_label.set_text(f'{total} companies')

    if empty_state:
        empty_state.set_visibility(total == 0)
        grid.set_visibility(total > 0)


def _add_entity_dialog(config, grid, status_label, empty_state=None):
    """Open dialog to add a new entity."""
    _entity_dialog(config, EntityConfig(), is_new=True, index=None,
                   grid=grid, status_label=status_label, empty_state=empty_state)


def _edit_entity_dialog(config, index, grid, status_label, empty_state=None):
    """Open dialog to edit an existing entity."""
    _entity_dialog(config, config.entities[index], is_new=False, index=index,
                   grid=grid, status_label=status_label, empty_state=empty_state)


def _delete_entity_dialog(config, index, grid, status_label, empty_state=None):
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

            ui.button('Delete', icon='delete', on_click=do_delete,
                      color=CLR_DANGER).props('outline')

    dlg.open()


def _entity_dialog(config, entity, is_new, index, grid, status_label, empty_state=None):
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

            async def on_test():
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
                    info_name.set_value(company)
                    info_remark.set_value(remark)
                    info_prefix.set_value(alias)
                    entity.name = company
                    entity.remark = remark
                    entity.prefix = alias

                    if detected_prefix and strip_prefix.value in ('', '300-'):
                        strip_prefix.set_value(detected_prefix)

                    msg = f'Connected! {company} (Alias: {alias})'
                    if sample_code:
                        msg += f' | Sample: {sample_code}'
                    status_banner(entity_test_result, msg, 'success')
                else:
                    status_banner(entity_test_result,
                                  'Connected but SY_PROFILE is empty.', 'warning')

            entity_test_btn.on_click(on_test)

            def on_save():
                path = (fb_path.value or '').strip()
                if not path:
                    ui.notify('FDB Path is required.', type='warning')
                    return

                # Check for duplicate FDB path
                for i, existing in enumerate(config.entities):
                    if i == index:
                        continue  # skip self when editing
                    if existing.fb_path and existing.fb_path.strip().lower() == path.lower():
                        name = existing.name or existing.prefix or f'Entity #{i + 1}'
                        ui.notify(f'This database is already added as "{name}".',
                                  type='warning')
                        return

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

            ui.button('Save', icon='save', on_click=on_save, color=CLR_PRIMARY)

    dialog.open()
