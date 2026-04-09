"""Sync Dashboard tab — preview, sync, progress, and log output."""

import threading
import time as _time
import pythoncom
from datetime import date, datetime
from nicegui import ui
from config import save_config
from sync_engine import SyncEngine, IMPORT_ORDER, _format_duration
from logger import SyncLogger
from shared import CLR_PRIMARY, CLR_DANGER


# Module keys → display labels (merged master + transactions)
ALL_MODULE_LABELS = {
    'Customer': 'Customer',
    'IV': 'Invoice',
    'DN': 'Debit Note',
    'CN': 'Credit Note',
    'CT': 'Contra',
    'PM': 'Payment',
    'CF': 'Refund',
}

# TXN-only labels (for log display)
TXN_LABELS = {
    'IV': 'Customer Invoice',
    'DN': 'Customer Debit Note',
    'CN': 'Customer Credit Note',
    'CT': 'Customer Contra',
    'PM': 'Customer Payment',
    'CF': 'Customer Refund',
}


def build_sync_tab(config, refresh_entity_list_fn=None):
    """Build the Sync Dashboard tab UI."""

    # --- State ---
    state = {
        'sync_engine': None,
        'sync_thread': None,
        'sync_mode': 'skip',
    }

    # --- Side-by-side: Config (left) | Log (right) ---
    with ui.row().classes('w-full gap-4 items-stretch'):

        # =============================================
        # LEFT CARD — Configuration + Actions
        # =============================================
        with ui.card().classes('flex-1 min-w-[350px]'):
            btns = {}
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Configuration').classes(
                    'text-base font-bold').style(f'color: {CLR_PRIMARY}')
                with ui.row().classes('gap-2'):
                    btns['preview'] = ui.button('Preview', icon='visibility',
                                                on_click=lambda: _run_preview(
                                                    config, state, entity_select, module_select,
                                                    date_from, date_to,
                                                    log, progress_bar, progress_label,
                                                    btns['preview'], btns['sync'], btns['cancel']),
                                                color=CLR_PRIMARY).props('outline')
                    btns['sync'] = ui.button('Start Sync', icon='sync',
                                             on_click=lambda: _run_sync(
                                                 config, state, entity_select, module_select,
                                                 date_from, date_to,
                                                 log, progress_bar, progress_label,
                                                 btns['preview'], btns['sync'], btns['cancel'],
                                                 refresh_entity_list_fn),
                                             color=CLR_PRIMARY)
                    btns['cancel'] = ui.button('Cancel', icon='cancel',
                                               on_click=lambda: _cancel_sync(state, progress_label),
                                               color=CLR_DANGER).props('outline')
                    btns['cancel'].set_enabled(False)
            ui.separator().classes('mb-2')

            with ui.grid(columns='70px minmax(0,1fr)').classes('w-full gap-y-3 items-center'):

                # Row 0: Source Companies (multi-select)
                ui.label('Source:').classes('text-sm font-medium')
                entity_options = {}
                for i, entity in enumerate(config.entities):
                    display = f"{entity.prefix or '?'} - {entity.name or '(not connected)'}"
                    entity_options[i] = display
                all_entity_keys = list(entity_options.keys())
                saved = config.last_sync_selection
                default_sel = [i for i in saved if i in entity_options] if saved else all_entity_keys
                if not default_sel:
                    default_sel = all_entity_keys
                entity_select = ui.select(
                    options=entity_options,
                    value=default_sel,
                    multiple=True,
                    with_input=True,
                ).classes('w-full').props('outlined dense use-chips')

                def _on_entity_change(e):
                    config.last_sync_selection = e.value if isinstance(e.value, list) else [e.value]
                    save_config(config)
                entity_select.on_value_change(_on_entity_change)

                # Row 1: Data modules (multi-select)
                ui.label('Data:').classes('text-sm font-medium')
                module_options = dict(ALL_MODULE_LABELS)
                all_module_keys = list(module_options.keys())
                module_select = ui.select(
                    options=module_options,
                    value=all_module_keys,
                    multiple=True,
                    with_input=True,
                ).classes('w-full').props('outlined dense use-chips')

                # Row 2: Date Range
                ui.label('Date:').classes('text-sm font-medium')
                with ui.row().classes('items-center gap-2 flex-nowrap'):
                    date_checkbox = ui.checkbox('', value=True)
                    date_from = ui.input(placeholder='DD/MM/YYYY').classes('w-32').props(
                        'outlined dense mask="##/##/####"')
                    ui.label('\u2014').classes('text-gray-400')
                    date_to = ui.input(placeholder='DD/MM/YYYY').classes('w-32').props(
                        'outlined dense mask="##/##/####"')

                    date_to.set_value(date.today().strftime('%d/%m/%Y'))
                    _set_default_date_from(config, date_from)

                    def on_date_toggle():
                        if not date_checkbox.value:
                            date_from.set_value('')
                            date_to.set_value('')
                        date_from.set_enabled(date_checkbox.value)
                        date_to.set_enabled(date_checkbox.value)

                    date_checkbox.on_value_change(on_date_toggle)

                # Row 3: Sync Mode
                ui.label('Mode:').classes('text-sm font-medium')
                sync_mode = ui.radio(
                    {'skip': 'Skip existing (recommended)', 'purge': 'Purge & Re-sync'},
                    value='skip',
                ).props('inline')
                sync_mode.on_value_change(lambda e: state.update({'sync_mode': e.value}))

            # --- Progress ---
            with ui.row().classes('w-full items-center gap-3 mt-3'):
                progress_bar = ui.linear_progress(value=0, show_value=False
                                                   ).classes('flex-grow').props(
                    f'color="{CLR_PRIMARY}" rounded size="8px"')
                progress_pct = ui.label('').classes('text-sm font-bold').style(
                    f'color: {CLR_PRIMARY}')
            progress_label = ui.label('Ready').classes('text-sm text-gray-500')


        # =============================================
        # RIGHT CARD — Sync Log
        # =============================================
        with ui.card().classes('flex-1 min-w-[400px] flex flex-col'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Sync Log').classes(
                    'text-base font-bold').style(f'color: {CLR_PRIMARY}')
                ui.button('Export', icon='download',
                          on_click=lambda: _export_log(log),
                          color=CLR_PRIMARY).props('flat')
            ui.separator().classes('mb-1')

            log = ui.log(max_lines=2000).classes('w-full flex-grow font-mono text-xs'
                                                  ).style('min-height: 300px')

    # Store progress_pct in state for callbacks
    state['progress_pct'] = progress_pct


def _set_default_date_from(config, date_from_input):
    """Set date from = earliest last_synced across all entities."""
    earliest = None
    for entity in config.entities:
        if entity.last_synced:
            try:
                dt = datetime.fromisoformat(entity.last_synced)
                if earliest is None or dt < earliest:
                    earliest = dt
            except (ValueError, TypeError):
                pass
    if earliest:
        date_from_input.set_value(earliest.strftime('%d/%m/%Y'))


def _parse_date(val: str):
    """Convert DD/MM/YYYY to YYYY-MM-DD for SQL, or return None if empty."""
    if not val or not val.strip():
        return None
    parts = val.strip().split('/')
    if len(parts) == 3:
        return f'{parts[2]}-{parts[1]}-{parts[0]}'
    return val


def _validate_date_range(df: str, dt: str) -> str:
    """Validate parsed YYYY-MM-DD date range. Returns error message or None."""
    for label, val in (('Date From', df), ('Date To', dt)):
        if val is None:
            continue
        try:
            datetime.strptime(val, '%Y-%m-%d')
        except (ValueError, TypeError):
            return f'{label} is not a valid date (expected DD/MM/YYYY).'
    if df and dt and df > dt:
        return 'Date From must be on or before Date To.'
    return None


def _get_selected_entities(config, entity_select):
    """Get entity objects from the multi-select dropdown."""
    selected_indices = entity_select.value or []
    if not isinstance(selected_indices, list):
        selected_indices = [selected_indices]
    return [config.entities[i] for i in selected_indices
            if 0 <= i < len(config.entities)]


def _get_selected_modules(module_select):
    """Get module keys from the multi-select dropdown, split into master + txn."""
    selected = module_select.value or []
    if not isinstance(selected, list):
        selected = [selected]
    sync_customers = 'Customer' in selected
    modules = [m for m in IMPORT_ORDER if m in selected]
    return sync_customers, modules


def _set_syncing(is_syncing, preview_btn, sync_btn, cancel_btn):
    preview_btn.set_enabled(not is_syncing)
    sync_btn.set_enabled(not is_syncing)
    cancel_btn.set_enabled(is_syncing)


def _run_preview(config, state, entity_select, module_select,
                 date_from, date_to,
                 log, progress_bar, progress_label,
                 preview_btn, sync_btn, cancel_btn):
    """Run preview in background thread."""
    entities = _get_selected_entities(config, entity_select)
    sync_customers, modules = _get_selected_modules(module_select)

    if not entities:
        ui.notify('Please select at least one source company.', type='warning')
        return
    if not modules and not sync_customers:
        ui.notify('Please select at least one data module.', type='warning')
        return

    is_purge = state['sync_mode'] == 'purge'
    df = _parse_date(date_from.value)
    dt = _parse_date(date_to.value)
    err = _validate_date_range(df, dt)
    if err:
        ui.notify(err, type='warning')
        return
    progress_pct = state.get('progress_pct')

    log.clear()
    progress_bar.set_value(0)
    if progress_pct:
        progress_pct.set_text('')
    _set_syncing(True, preview_btn, sync_btn, cancel_btn)

    def _log_callback(level, message):
        prefix = {'ERROR': '[ERROR] ', 'WARNING': '[WARN]  ',
                  'SUCCESS': '[OK]    '}.get(level, '[INFO]  ')
        log.push(f'{prefix}{message}')

    def _progress_callback(current, total, message):
        if total > 0:
            pct = current / total
            progress_bar.set_value(pct)
            if progress_pct:
                progress_pct.set_text(f'{int(pct * 100)}%')
        progress_label.set_text(f'{message} ({current}/{total})')

    def _thread():
        pythoncom.CoInitialize()
        try:
            logger = SyncLogger(log_callback=_log_callback)
            engine = SyncEngine(config, logger, _progress_callback)

            if is_purge:
                logger.info('Starting comparison preview (Purge & Re-sync)...')
                results = engine.compare_documents(entities, modules, df, dt)
                logger.info('=' * 50)
                logger.info('COMPARISON RESULTS')
                logger.info('=' * 50)
                for r in results:
                    logger.info(f"Entity: {r['entity_name']} (Prefix: {r['prefix']})")
                    for mod, data in r['modules'].items():
                        matched = data['source_count'] - len(data['new']) - len(data['changed'])
                        logger.info(f"  {mod}: {data['source_count']} in source, "
                                    f"{data['consol_count']} in consol")
                        if matched > 0:
                            logger.info(f'    Matched: {matched}')
                        if data['new']:
                            logger.info(f"    New in source: {len(data['new'])}")
                        if data['changed']:
                            logger.info(f"    Changed: {len(data['changed'])}")
                            for c in data['changed'][:5]:
                                logger.info(f"      {c['doc_no']}: {c['diffs']}")
                            if len(data['changed']) > 5:
                                logger.info(f"      ... and {len(data['changed'])-5} more")
                        if data['deleted']:
                            logger.info(f"    Deleted from source: {len(data['deleted'])}")
            else:
                logger.info('Starting preview (dry run)...')
                results = engine.preview(entities, modules, df, dt)
                logger.info('=' * 50)
                logger.info('PREVIEW RESULTS')
                logger.info('=' * 50)
                for r in results:
                    logger.info(f'Entity: {r.entity_name} (Prefix: {r.prefix})')
                    logger.info(f'  Customers: {r.customer_count}')
                    for mod, count in r.doc_counts.items():
                        status = str(count) if count >= 0 else 'ERROR'
                        logger.info(f'  {mod}: {status}')

            _set_syncing(False, preview_btn, sync_btn, cancel_btn)
            progress_label.set_text('Preview complete')
        finally:
            logger.close()
            pythoncom.CoUninitialize()

    t = threading.Thread(target=_thread, daemon=True)
    state['sync_thread'] = t
    t.start()


async def _run_sync(config, state, entity_select, module_select,
                    date_from, date_to,
                    log, progress_bar, progress_label,
                    preview_btn, sync_btn, cancel_btn,
                    refresh_entity_list_fn):
    """Run sync in background thread with confirmation dialog."""
    entities = _get_selected_entities(config, entity_select)
    sync_customers, modules = _get_selected_modules(module_select)

    if not entities:
        ui.notify('Please select at least one source company.', type='warning')
        return
    if not modules and not sync_customers:
        ui.notify('Please select at least one data module.', type='warning')
        return

    is_purge = state['sync_mode'] == 'purge'

    df = _parse_date(date_from.value)
    dt = _parse_date(date_to.value)
    err = _validate_date_range(df, dt)
    if err:
        ui.notify(err, type='warning')
        return

    confirmed = await _confirm_sync(entities, modules, is_purge)
    if not confirmed:
        return

    progress_pct = state.get('progress_pct')

    log.clear()
    progress_bar.set_value(0)
    if progress_pct:
        progress_pct.set_text('')
    _set_syncing(True, preview_btn, sync_btn, cancel_btn)

    def _log_callback(level, message):
        prefix = {'ERROR': '[ERROR] ', 'WARNING': '[WARN]  ',
                  'SUCCESS': '[OK]    '}.get(level, '[INFO]  ')
        log.push(f'{prefix}{message}')

    def _progress_callback(current, total, message):
        if total > 0:
            pct = current / total
            progress_bar.set_value(pct)
            if progress_pct:
                progress_pct.set_text(f'{int(pct * 100)}%')
        progress_label.set_text(f'{message} ({current}/{total})')

    def _thread():
        pythoncom.CoInitialize()
        try:
            logger = SyncLogger(log_callback=_log_callback)
            mode_label = 'Purge & Re-sync' if is_purge else 'sync'
            logger.info(f'Starting {mode_label}...')

            engine = SyncEngine(config, logger, _progress_callback)
            state['sync_engine'] = engine
            sync_start = _time.time()

            results = engine.sync(
                entities, modules,
                date_from=df, date_to=dt,
                sync_customers=sync_customers,
                purge_resync=is_purge,
            )
            total_duration = _format_duration(_time.time() - sync_start)

            logger.info('=' * 50)
            logger.info('SYNC RESULTS SUMMARY')
            logger.info('=' * 50)
            for r in results:
                logger.info(f'Entity: {r.entity_name} (Prefix: {r.prefix})')
                logger.info(f'  Customers: {r.customers_synced} synced, '
                            f'{r.customers_skipped} skipped, {r.customers_failed} failed')
                for mod in IMPORT_ORDER:
                    s = r.docs_synced.get(mod, 0)
                    sk = r.docs_skipped.get(mod, 0)
                    f = r.docs_failed.get(mod, 0)
                    if s or sk or f:
                        logger.info(f'  {mod}: {s} synced, {sk} skipped, {f} failed')
                if r.errors:
                    for err in r.errors:
                        logger.error(f'  Error: {err}')

            logger.info(f'Total sync duration: {total_duration}')

            _set_syncing(False, preview_btn, sync_btn, cancel_btn)
            progress_label.set_text('Sync complete')
            state['sync_engine'] = None

            if refresh_entity_list_fn:
                refresh_entity_list_fn()
        finally:
            logger.close()
            pythoncom.CoUninitialize()

    t = threading.Thread(target=_thread, daemon=True)
    state['sync_thread'] = t
    t.start()


async def _confirm_sync(entities, modules, is_purge):
    """Show confirmation dialog and return True if user confirms."""
    result = {'confirmed': False}

    with ui.dialog() as dlg, ui.card():
        if is_purge:
            ui.label('Purge & Re-sync').classes('text-base font-bold text-red-600')
            ui.label(
                f'This will DELETE and re-import all documents for '
                f'{len(entities)} company(ies) in the selected date range.\n\n'
                'Please ensure you have backed up the consolidation database.'
            ).classes('whitespace-pre-wrap text-sm')
            with ui.row().classes('justify-end w-full mt-4 gap-2'):
                ui.button('Cancel', on_click=dlg.close).props('flat')

                def confirm():
                    result['confirmed'] = True
                    dlg.close()
                ui.button('Proceed with Purge', icon='warning',
                          on_click=confirm, color=CLR_DANGER).props('outline')
        else:
            ui.label('Confirm Sync').classes('text-base font-bold')
            ui.label(
                f"Sync {len(entities)} company(ies) with {len(modules)} module(s)?\n\n"
                'Please ensure you have backed up the consolidation database.'
            ).classes('whitespace-pre-wrap text-sm')
            with ui.row().classes('justify-end w-full mt-4 gap-2'):
                ui.button('Cancel', on_click=dlg.close).props('flat')

                def confirm():
                    result['confirmed'] = True
                    dlg.close()
                ui.button('Start Sync', icon='sync',
                          on_click=confirm, color=CLR_PRIMARY)

    await dlg
    return result['confirmed']


def _cancel_sync(state, progress_label):
    """Cancel the running sync."""
    if state.get('sync_engine'):
        state['sync_engine'].cancel()
        progress_label.set_text('Cancelling...')


async def _export_log(log):
    """Export log content as a .log file download in the browser."""
    content = await ui.run_javascript(f'''
        const el = getElement({log.id}).$el;
        return el ? el.innerText : '';
    ''')
    if not content or not content.strip():
        ui.notify('Log is empty — nothing to export.', type='warning')
        return
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'sync_{timestamp}.log'
    ui.download(content.encode('utf-8'), filename)
