"""Entity Manager tab — source entity CRUD with AG Grid."""

import re
import fdb
from nicegui import ui, run, events
from config import EntityConfig, save_config
from shared import CLR_PRIMARY, CLR_SECONDARY, CLR_ACCENT, CLR_DANGER, AG_GRID_STYLE, _set_checked_filtered


def build_entity_tab(config, on_entities_changed=None):
    """Build the Entity Manager tab UI.

    Args:
        config: AppConfig instance
        on_entities_changed: optional callback when entities are added/removed/toggled
    """

    ui.add_body_html(AG_GRID_STYLE)

    status_label = ui.label('').classes('text-sm text-gray-500 ml-1')

    grid = ui.aggrid({
        'columnDefs': [
            {
                'headerName': '\u2611',
                'field': 'enabled',
                'cellDataType': 'boolean',
                'editable': True,
                'filter': True,
                'width': 60,
                'suppressSizeToFit': True,
            },
            {
                'headerName': '#',
                'field': 'row_num',
                'width': 60,
                'filter': 'agNumberColumnFilter',
            },
            {
                'headerName': 'Prefix',
                'field': 'prefix',
                'width': 90,
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
                'width': 80,
                'filter': 'agTextColumnFilter',
            },
            {
                'headerName': 'Last Synced',
                'field': 'last_synced',
                'width': 160,
                'filter': 'agTextColumnFilter',
            },
        ],
        'rowData': [],
        'animateRows': False,
        'defaultColDef': {
            'resizable': True,
            'sortable': True,
            'filterParams': {'buttons': ['reset']},
        },
    }, theme='quartz', auto_size_columns=False).style('height: 400px')

    grid.on('cellDoubleClicked', lambda e: _on_row_double_click(e, config, grid,
                                                                 status_label, on_entities_changed))
    grid.on('cellValueChanged', lambda e: _on_enabled_changed(e, config, grid, on_entities_changed))

    with ui.row().classes('justify-center mt-4'):
        ui.button('Check All',
                  on_click=lambda: _set_checked_filtered(grid, 'enabled', True),
                  color=CLR_SECONDARY).props('dense size=sm')
        ui.button('Uncheck All',
                  on_click=lambda: _set_checked_filtered(grid, 'enabled', False),
                  color=CLR_SECONDARY).props('dense size=sm outline')
        ui.button('+ Add Entity',
                  on_click=lambda: _add_entity_dialog(config, grid, status_label, on_entities_changed),
                  color=CLR_PRIMARY)
        ui.button('Remove Checked',
                  on_click=lambda: _remove_selected(config, grid, status_label, on_entities_changed),
                  color=CLR_DANGER)

    # Initial data load
    _refresh_grid(config, grid, status_label)

    return grid, status_label


def _refresh_grid(config, grid, status_label):
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
            'enabled': entity.enabled,
            '_index': i,
        })

    grid.options['rowData'] = row_data
    grid.update()

    total = len(config.entities)
    enabled = sum(1 for e in config.entities if e.enabled)
    status_label.set_text(f'{total} entities, {enabled} enabled')


async def _on_enabled_changed(e, config, grid, on_entities_changed):
    """Handle enabled checkbox toggle — update entity enabled state."""
    row = e.args.get('data', {})
    idx = row.get('_index')
    if idx is not None and 0 <= idx < len(config.entities):
        config.entities[idx].enabled = bool(row.get('enabled', False))
        save_config(config)
        if on_entities_changed:
            on_entities_changed()


async def _on_row_double_click(e, config, grid, status_label, on_entities_changed):
    """Open edit dialog on row double-click."""
    row = e.args.get('data', {})
    idx = row.get('_index')
    if idx is not None and 0 <= idx < len(config.entities):
        _edit_entity_dialog(config, idx, grid, status_label, on_entities_changed)


def _add_entity_dialog(config, grid, status_label, on_entities_changed):
    """Open dialog to add a new entity."""
    _entity_dialog(config, EntityConfig(), is_new=True, index=None,
                   grid=grid, status_label=status_label,
                   on_entities_changed=on_entities_changed)


def _edit_entity_dialog(config, index, grid, status_label, on_entities_changed):
    """Open dialog to edit an existing entity."""
    _entity_dialog(config, config.entities[index], is_new=False, index=index,
                   grid=grid, status_label=status_label,
                   on_entities_changed=on_entities_changed)


def _entity_dialog(config, entity, is_new, index, grid, status_label, on_entities_changed):
    """Show add/edit entity dialog."""
    title = 'Add Source Entity' if is_new else 'Edit Source Entity'

    with ui.dialog() as dialog, ui.card().classes('w-[650px]'):
        ui.label(title).classes('text-lg font-bold').style(f'color: {CLR_PRIMARY}')

        # --- Firebird Connection ---
        ui.label('Firebird Connection (Source DB)').classes('font-bold mt-2')

        with ui.grid(columns=2).classes('w-full gap-y-1 gap-x-4 items-center'):
            ui.label('FDB Path:').classes('font-bold')
            fb_path = ui.input(value=entity.fb_path,
                               placeholder='e.g. C:\\eStream\\SQLAccounting\\DB\\ACC-0001.FDB'
                               ).classes('w-96').tooltip(
                'Full path to the source .FDB file')

            ui.label('Firebird Host:').classes('font-bold')
            fb_host = ui.input(value=entity.fb_host,
                               placeholder='localhost').classes('w-96')

            ui.label('Firebird User:').classes('font-bold')
            fb_user = ui.input(value=entity.fb_user,
                               placeholder='SYSDBA').classes('w-96')

            ui.label('Firebird Password:').classes('font-bold')
            fb_pass = ui.input(value=entity.fb_password,
                               placeholder='masterkey', password=True,
                               password_toggle_button=True).classes('w-96')

        # --- Transformation ---
        ui.label('Transformation Settings').classes('font-bold mt-4')

        with ui.grid(columns=2).classes('w-full gap-y-1 gap-x-4 items-center'):
            ui.label('Customer Code Prefix to Strip:').classes('font-bold')
            strip_prefix = ui.input(value=entity.customer_code_prefix,
                                    placeholder='e.g. 300-').classes('w-96').tooltip(
                'e.g. if customer code is 300-A0001, then prefix is 300-')

        # --- Auto-read info ---
        ui.label('Auto-Read Info (from Company Profile)').classes('font-bold mt-4')

        with ui.grid(columns=2).classes('w-full gap-y-1 gap-x-4 items-center'):
            ui.label('Company Name:').classes('font-bold')
            info_name = ui.input(value=entity.name or '(click Test Connection)'
                                 ).classes('w-96').props('readonly')

            ui.label('Remark:').classes('font-bold')
            info_remark = ui.input(value=entity.remark or '(click Test Connection)'
                                   ).classes('w-96').props('readonly')

            ui.label('Entity Prefix (ALIAS):').classes('font-bold')
            info_prefix = ui.input(value=entity.prefix or '(click Test Connection)'
                                   ).classes('w-96').props('readonly').tooltip(
                'SQL Account: File > Company Profile > More > Short Company Name')

        # --- Buttons ---
        with ui.row().classes('justify-center mt-4 w-full'):
            async def on_test():
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

                if error:
                    ui.notify(f'Connection failed: {error}', type='negative', multi_line=True)
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

                    msg = f'Connected! Company: {company}, Alias: {alias}'
                    if sample_code:
                        msg += f' | Sample Code: {sample_code}'
                        if detected_prefix:
                            msg += f' (detected prefix: {detected_prefix})'
                    ui.notify(msg, type='positive')
                else:
                    ui.notify('Connected but SY_PROFILE is empty.', type='warning')

            def on_save():
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
                _refresh_grid(config, grid, status_label)
                if on_entities_changed:
                    on_entities_changed()
                dialog.close()
                ui.notify('Entity saved.', type='positive')

            ui.button('Test Connection', on_click=on_test, color=CLR_ACCENT)
            ui.button('Save', on_click=on_save, color=CLR_PRIMARY)
            ui.button('Cancel', on_click=dialog.close).props('flat')

    dialog.open()


async def _remove_selected(config, grid, status_label, on_entities_changed):
    """Remove checked entities."""
    all_rows = await grid.get_client_data()
    rows = [r for r in all_rows if r.get('enabled')]
    if not rows:
        ui.notify('Please check entities to remove.', type='warning')
        return

    with ui.dialog() as confirm, ui.card():
        ui.label(f'Remove {len(rows)} entity(ies)?').classes('text-lg')
        with ui.row().classes('justify-end w-full'):
            ui.button('Cancel', on_click=confirm.close).props('flat')

            def do_remove():
                indices = sorted([r['_index'] for r in rows], reverse=True)
                for idx in indices:
                    config.remove_entity(idx)
                save_config(config)
                _refresh_grid(config, grid, status_label)
                if on_entities_changed:
                    on_entities_changed()
                confirm.close()
                ui.notify(f'Removed {len(indices)} entity(ies).', type='positive')

            ui.button('Remove', on_click=do_remove, color=CLR_DANGER)

    confirm.open()
