#### Release Build 5 – 15 Apr 2026

1. Setup tab: Save (Consolidation DB) now auto-runs Test Connection first — both SDK and direct Firebird tests must pass before the settings are saved, preventing invalid configs
2. Setup tab: Save (Source Company) now auto-runs Test Connection first — save is blocked if the Firebird connection fails or SY_PROFILE is empty
3. Setup tab: Save (Source Company) now blocks duplicate prefix (ALIAS) — prevents saving a source DB whose ALIAS conflicts with another configured source, because duplicate prefixes cause document number collisions in the consolidation DB
4. Setup tab: Source Companies grid now highlights duplicate prefixes in red so conflicts are visible at a glance
5. Setup tab: New "Refresh" button (next to + Add Company) re-fetches ALIAS / company name / remark from every configured source DB and updates the grid — use this after changing ALIASes in SQL Account to spot conflicts without opening each source company
6. Sync tab: Preview and Start Sync now validate that ALL configured source DBs have unique live ALIASes from SQL Account (not just the selected subset) — syncing a single source is blocked if its current ALIAS collides with another configured source, because the consolidation DB already uses that prefix
7. Sync tab: Sync log shows live vs stored ALIAS for each source DB during validation, making ALIAS changes made in SQL Account visible

#### Release Build 4 – 12 Apr 2026

1. App now auto-shuts down 30 seconds after the browser is closed — prevents lingering background process that blocked exe replacement during upgrades
2. Page reloads and accidental tab closes are safe — the shutdown timer is cancelled if the browser reconnects within the grace period
3. Installer now force-kills any lingering SQLAccConsolSync.exe before installing, as a safeguard for upgrading from older versions without auto-shutdown

#### Release Build 3 – 12 Apr 2026

1. Setup tab: Test Connection and Save notifications now display as inline banners below the header (near buttons) instead of bottom-of-page toasts that users missed
2. Sync tab: Added date picker (calendar icon) beside date fields for mouse-friendly date entry
3. Sync tab: Fixed date field typing bug — focusing a pre-filled date field now clears it for fresh input; previous value restores on blur if nothing was typed
4. Category tab: Source company dropdown now refreshes automatically after adding, editing, or removing a source company in Setup tab (no browser refresh needed)
5. Sync tab: Source company multi-select also refreshes automatically on entity changes

#### Release Build 2 – 09 Apr 2026

1. Migrated UI from CustomTkinter to NiceGUI (web-based, opens in default browser)
2. Tab structure consolidated to 3 tabs: Setup | Categories | Sync
3. Setup tab combines Consolidation DB config + Source Companies grid in a side-by-side layout
4. Test Connection now performs a two-phase test (SDK login + Direct DB connection)
5. Sync tab uses multi-select dropdowns for source companies and data modules
6. Source company selection in Sync tab is remembered between sessions
7. Date range validation rejects reversed (Date From > Date To) dates
8. Categories tab: searchable category dropdown in grid cells, bulk assign to ticked rows
9. Renamed: "Settings" → "Setup", "Category Mapping" → "Categories", "Check All/Uncheck All" → "Tick All/Un-tick All", "Add Entity" → "+ Add Company", "Entity" → "Source Company"
10. Improved error logging — warnings for unparseable dates and knock-off read failures
11. Hardened SQL input validation with whitelist for prefix, doctype, and date params
12. Config file gracefully ignores unknown keys (forward-compat)
13. Bundled customized FastReport (.fr3) for the consolidated 12-Month Customer Statement of Account grouped by Company Category — see User Guide → Database Prerequisites for import steps
14. Removed legacy CustomTkinter UI files (ui_app.py, tab_settings.py, tab_entity.py)

#### Release Build 1 – 20 Mar 2026

1. Initial release — AR document sync (IV, DN, CN, CT, PM, CF)
2. Multi-currency support with auto-creation (currency, GL account, payment method)
3. Customer master data sync with category mapping
4. Skip existing / Purge & Re-sync modes
5. Opening balance support (SystemConversionDate handling)
6. Tax code validation (SST/GST)
7. Category Mapping tab with filter, pagination, and batch operations
8. Unmapped customer filtering (skip customers without category assignment)
9. Preview / dry-run mode with record counts
10. Purge comparison preview (changed, new, deleted documents)
11. Date range filtering for sync operations
