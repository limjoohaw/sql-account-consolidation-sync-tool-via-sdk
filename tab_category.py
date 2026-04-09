"""Categories tab — AG Grid with virtual scrolling for 10k+ customers."""

import fdb
from nicegui import ui, run
from config import save_config
from shared import CLR_PRIMARY, AG_GRID_STYLE, _set_checked_filtered


def build_category_tab(config, get_company_categories):
    """Build the Categories tab UI.

    Args:
        config: AppConfig instance
        get_company_categories: callable that returns list of {'code', 'description'}
    """

    ui.add_body_html(AG_GRID_STYLE)

    # --- State ---
    state = {
        'entity_idx': -1,
        'customers': [],         # [(code, name, currency), ...]
        'cat_values': ['(none)'],
        'categories': [],        # [{'code': ..., 'description': ...}, ...]
    }

    # --- Row 1: Source (left) + Bulk Assign (right), buttons beside dropdowns ---
    with ui.row().classes('w-full gap-4 items-center flex-nowrap'):
        # Left half: Source + Load Customers
        with ui.row().classes('flex-1 items-center gap-2 min-w-0 flex-nowrap'):
            ui.label('Source:').classes('text-sm font-medium flex-shrink-0')
            entity_select = ui.select(
                options={}, value=None, with_input=True,
            ).classes('flex-grow min-w-0').props('outlined dense')
            ui.button('Load Customers', icon='download',
                      on_click=lambda: load_customers(config, state, entity_select,
                                                       grid, status_label,
                                                       get_company_categories, bulk_select,
                                                       empty_state),
                      color=CLR_PRIMARY).classes('flex-shrink-0')

        # Right half: Bulk Assign + Apply to Checked
        with ui.row().classes('flex-1 items-center gap-2 min-w-0 flex-nowrap'):
            ui.label('Bulk Assign:').classes('text-sm font-medium flex-shrink-0')
            bulk_select = ui.select(
                options=['(load categories first)'], value='(load categories first)',
                with_input=True,
            ).classes('flex-grow min-w-0').props('outlined dense')
            ui.button('Apply to Checked', icon='playlist_add_check',
                      on_click=lambda: bulk_apply(grid, bulk_select, state),
                      color=CLR_PRIMARY).classes('flex-shrink-0')

    # --- Row 2: Action buttons ---
    with ui.row().classes('w-full justify-between items-center mt-1'):
        with ui.row().classes('gap-2'):
            ui.button('Tick All', icon='check',
                      on_click=lambda: _set_checked_filtered(grid, 'checked', True),
                      color=CLR_PRIMARY).props('flat')
            ui.button('Un-tick All', icon='close',
                      on_click=lambda: _set_checked_filtered(grid, 'checked', False),
                      ).props('outline').style('color: grey')
        with ui.row().classes('gap-2'):
            ui.button('Refresh Categories', icon='refresh',
                      on_click=lambda: load_categories(config, state, bulk_select,
                                                        grid, get_company_categories),
                      color=CLR_PRIMARY).props('outline')
            ui.button('Save Mapping', icon='save',
                      on_click=lambda: save_mapping(config, grid, state, status_label),
                      color=CLR_PRIMARY)

    # --- Empty state (before load) ---
    empty_state = ui.column().classes('w-full items-center justify-center py-12')
    with empty_state:
        ui.icon('category', size='xl', color='grey-5')
        ui.label('Select a source company and click Load Customers').classes(
            'text-sm text-gray-500 mt-2')

    # --- AG Grid ---
    grid = ui.aggrid({
        'columnDefs': [
            {
                'headerName': '\u2611',
                'field': 'checked',
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
                'headerName': 'Customer Code',
                'field': 'code',
                'width': 140,
                'filter': 'agTextColumnFilter',
                'filterParams': {
                    'filterOptions': ['contains'],
                    'suppressAndOrCondition': True,
                },
            },
            {
                'headerName': 'Company Name',
                'field': 'name',
                'flex': 1,
                'filter': 'agTextColumnFilter',
                'filterParams': {
                    'filterOptions': ['contains'],
                    'suppressAndOrCondition': True,
                },
            },
            {
                'headerName': 'Curr',
                'field': 'currency',
                'width': 70,
                'filter': 'agTextColumnFilter',
            },
            {
                'headerName': 'Category',
                'field': 'category',
                'width': 280,
                'cellRendererParams': {'values': ['(none)']},
                ':cellRenderer': '''params => {
                    const cell = document.createElement('div');
                    cell.style.cssText = 'position:relative;width:100%;height:100%;display:flex;align-items:center;cursor:pointer;user-select:none;';
                    const label = document.createElement('span');
                    label.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 2px;';
                    label.textContent = params.value || '(none)';
                    const arrow = document.createElement('span');
                    arrow.textContent = '\u25be';
                    arrow.style.cssText = 'padding:0 4px;color:#999;font-size:11px;';
                    cell.appendChild(label);
                    cell.appendChild(arrow);

                    cell.addEventListener('click', e => {
                        e.stopPropagation();
                        document.querySelectorAll('.cat-dropdown').forEach(el => el.remove());
                        const rect = cell.getBoundingClientRect();
                        const popup = document.createElement('div');
                        popup.className = 'cat-dropdown';
                        const below = window.innerHeight - rect.bottom > 220;
                        popup.style.cssText = 'position:fixed;z-index:9999;background:#fff;border:1px solid #ccc;border-radius:4px;box-shadow:0 4px 12px rgba(0,0,0,.15);display:flex;flex-direction:column;width:' + Math.max(rect.width, 280) + 'px;max-height:260px;left:' + rect.left + 'px;' + (below ? 'top:' + rect.bottom + 'px;' : 'bottom:' + (window.innerHeight - rect.top) + 'px;');

                        const search = document.createElement('input');
                        search.placeholder = 'Type to filter...';
                        search.style.cssText = 'padding:7px 8px;border:none;border-bottom:1px solid #e0e0e0;outline:none;font-size:13px;font-family:inherit;';
                        popup.appendChild(search);

                        const list = document.createElement('div');
                        list.style.cssText = 'overflow-y:auto;flex:1;';
                        popup.appendChild(list);

                        const values = params.colDef.cellRendererParams?.values || ['(none)'];
                        const current = params.value || '(none)';
                        function render(filter) {
                            list.innerHTML = '';
                            const q = (filter || '').toLowerCase();
                            const items = q ? values.filter(v => v.toLowerCase().includes(q)) : values;
                            items.forEach(v => {
                                const row = document.createElement('div');
                                row.textContent = v;
                                const isCur = v === current;
                                row.style.cssText = 'padding:5px 8px;cursor:pointer;font-size:13px;' + (isCur ? 'background:#E8E4F8;font-weight:600;' : '');
                                row.addEventListener('mouseenter', () => { if (!isCur) row.style.background = '#f5f3ff'; });
                                row.addEventListener('mouseleave', () => { row.style.background = isCur ? '#E8E4F8' : ''; });
                                row.addEventListener('click', () => {
                                    params.node.setDataValue(params.colDef.field, v);
                                    label.textContent = v;
                                    close();
                                });
                                list.appendChild(row);
                            });
                            if (!items.length) {
                                const empty = document.createElement('div');
                                empty.textContent = 'No matches';
                                empty.style.cssText = 'padding:8px;color:#999;font-size:13px;text-align:center;';
                                list.appendChild(empty);
                            }
                        }
                        search.addEventListener('input', () => render(search.value));
                        render('');

                        function close() { popup.remove(); document.removeEventListener('mousedown', outsideClick, true); }
                        function outsideClick(evt) { if (!popup.contains(evt.target)) close(); }
                        setTimeout(() => document.addEventListener('mousedown', outsideClick, true), 0);
                        search.addEventListener('keydown', evt => { if (evt.key === 'Escape') close(); });

                        document.body.appendChild(popup);
                        search.focus();
                    });
                    return cell;
                }''',
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
        ':getRowId': 'params => params.data.code',
    }, theme='quartz', auto_size_columns=False).style('height: 420px')

    # Hide grid initially (show empty state)
    grid.set_visibility(False)

    # --- Status label (after grid) ---
    status_label = ui.label('').classes('text-sm text-gray-500 mt-1')

    # Populate entity dropdown
    _refresh_entity_options(config, entity_select)

    return grid, state


def _refresh_entity_options(config, entity_select):
    """Refresh the entity selector options."""
    options = {}
    for i, entity in enumerate(config.entities):
        display = f"{entity.prefix or '?'} - {entity.name or '(not connected)'}"
        options[i] = display
    entity_select.options = options
    if options:
        entity_select.value = list(options.keys())[0]
    entity_select.update()


def _code_to_display(cat_code, cat_values):
    """Convert a category code to its display value (e.g. 'CAT1' -> 'CAT1 - Description')."""
    if not cat_code:
        return '(none)'
    for cv in cat_values:
        if cv.startswith(f'{cat_code} - ') or cv == cat_code:
            return cv
    return '(none)'


async def load_customers(config, state, entity_select, grid, status_label,
                         get_company_categories, bulk_select, empty_state=None):
    """Load customers from the selected entity's source DB."""
    idx = entity_select.value
    if idx is None or idx < 0 or idx >= len(config.entities):
        ui.notify('Please select a source company first.', type='warning')
        return

    entity = config.entities[idx]
    state['entity_idx'] = idx

    if not entity.fb_path:
        ui.notify('This company has no database path configured. Set it up in the Setup tab.',
                  type='warning')
        return

    status_label.set_text('Loading customers...')

    def _read():
        conn = fdb.connect(
            host=entity.fb_host,
            database=entity.fb_path,
            user=entity.fb_user,
            password=entity.fb_password,
            charset='UTF8',
        )
        try:
            cur = conn.cursor()
            try:
                cur.execute('SELECT CODE, COMPANYNAME, CURRENCYCODE '
                            'FROM AR_CUSTOMER ORDER BY CODE')
                customers = []
                for row in cur.fetchall():
                    code = (row[0] or '').strip()
                    name = (row[1] or '').strip()
                    currency = (row[2] or '').strip()
                    if code:
                        customers.append((code, name, currency))
                return customers
            finally:
                cur.close()
        finally:
            conn.close()

    try:
        customers = await run.io_bound(_read)
    except Exception as e:
        ui.notify(f'Could not read customers: {e}', type='negative', multi_line=True)
        status_label.set_text('Failed to load customers.')
        return

    state['customers'] = customers

    # Auto-load categories (always refresh on load)
    categories = get_company_categories(config)
    if categories:
        state['categories'] = categories
        cat_values = ['(none)'] + [f"{c['code']} - {c['description']}" for c in categories]
        state['cat_values'] = cat_values
        bulk_select.options = cat_values
        bulk_select.value = '(none)'
        bulk_select.update()
        for col in grid.options['columnDefs']:
            if col.get('field') == 'category':
                col['cellRendererParams'] = {'values': cat_values}

    # Build row data
    cat_values = state['cat_values']
    row_data = []
    mapped_count = 0
    for i, (code, name, currency) in enumerate(customers):
        saved_cat = entity.customer_category_map.get(code, '')
        display_cat = _code_to_display(saved_cat, cat_values)
        if display_cat != '(none)':
            mapped_count += 1
        row_data.append({
            'checked': False,
            'row_num': i + 1,
            'code': code,
            'name': name,
            'currency': currency,
            'category': display_cat,
        })

    grid.options['rowData'] = row_data
    grid.update()

    # Show grid, hide empty state
    grid.set_visibility(True)
    if empty_state:
        empty_state.set_visibility(False)

    total = len(customers)
    unmapped = total - mapped_count
    status_label.set_text(f'{total} customers, {mapped_count} mapped, {unmapped} unmapped')


async def load_categories(config, state, bulk_select, grid, get_company_categories):
    """Refresh company categories from consol DB."""
    categories = get_company_categories(config)

    if not categories:
        ui.notify('Could not load categories. Configure Consol DB in Setup first.',
                  type='warning')
        return

    state['categories'] = categories
    cat_values = ['(none)'] + [f"{c['code']} - {c['description']}" for c in categories]
    state['cat_values'] = cat_values

    bulk_select.options = cat_values
    bulk_select.value = '(none)'
    bulk_select.update()

    for col in grid.options['columnDefs']:
        if col.get('field') == 'category':
            col['cellRendererParams'] = {'values': cat_values}
    grid.update()

    ui.notify(f'Refreshed {len(categories)} company categories.', type='positive')


async def bulk_apply(grid, bulk_select, state):
    """Apply the bulk category selection to checked rows."""
    bulk_val = bulk_select.value
    if not bulk_val or bulk_val == '(load categories first)':
        ui.notify('Please select a category to apply.', type='warning')
        return

    # Run entirely in JS to avoid circular reference on Python round-trip
    count = await ui.run_javascript(f'''
        const gridEl = getElement({grid.id});
        let count = 0;
        gridEl.api.forEachNode(node => {{
            if (node.data && node.data.checked) {{
                node.setDataValue('category', {_js_str(bulk_val)});
                count++;
            }}
        }});
        return count;
    ''')

    if count and count > 0:
        ui.notify(f'Applied "{bulk_val}" to {count} customer(s).', type='positive')
    else:
        ui.notify('Please tick customer rows first.', type='warning')


def _js_str(val):
    """Escape a Python string for safe embedding in JavaScript."""
    return "'" + str(val).replace("\\", "\\\\").replace("'", "\\'") + "'"


async def save_mapping(config, grid, state, status_label):
    """Save the current customer-to-category mapping to config."""
    idx = state['entity_idx']
    if idx < 0 or idx >= len(config.entities):
        ui.notify('Please load customers first.', type='warning')
        return

    entity = config.entities[idx]

    rows = await grid.get_client_data()

    new_map = {}
    mapped = 0
    unmapped = 0

    for row in rows:
        code = row.get('code', '')
        cat_display = row.get('category', '(none)')
        if cat_display and cat_display != '(none)':
            cat_code = cat_display.split(' - ', 1)[0].strip()
            new_map[code] = cat_code
            mapped += 1
        else:
            unmapped += 1

    entity.customer_category_map = new_map
    save_config(config)

    total = mapped + unmapped
    status_label.set_text(f'{total} customers, {mapped} mapped, {unmapped} unmapped')
    ui.notify(f"Mapping saved for '{entity.name}'. "
              f"{mapped} mapped, {unmapped} unmapped.", type='positive')
