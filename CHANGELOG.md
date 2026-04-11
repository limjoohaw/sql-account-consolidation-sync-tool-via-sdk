Release Build 3 – 12 Apr 2026
01. Setup tab: Test Connection and Save notifications now display as inline banners below the header (near buttons) instead of bottom-of-page toasts that users missed
02. Sync tab: Added date picker (calendar icon) beside date fields for mouse-friendly date entry
03. Sync tab: Fixed date field typing bug — focusing a pre-filled date field now clears it for fresh input; previous value restores on blur if nothing was typed
04. Category tab: Source company dropdown now refreshes automatically after adding, editing, or removing a source company in Setup tab (no browser refresh needed)
05. Sync tab: Source company multi-select also refreshes automatically on entity changes

Release Build 2 – 09 Apr 2026
01. Migrated UI from CustomTkinter to NiceGUI (web-based, opens in default browser)
02. Tab structure consolidated to 3 tabs: Setup | Categories | Sync
03. Setup tab combines Consolidation DB config + Source Companies grid in a side-by-side layout
04. Test Connection now performs a two-phase test (SDK login + Direct DB connection)
05. Sync tab uses multi-select dropdowns for source companies and data modules
06. Source company selection in Sync tab is remembered between sessions
07. Date range validation rejects reversed (Date From > Date To) dates
08. Categories tab: searchable category dropdown in grid cells, bulk assign to ticked rows
09. Renamed: "Settings" → "Setup", "Category Mapping" → "Categories", "Check All/Uncheck All" → "Tick All/Un-tick All", "Add Entity" → "+ Add Company", "Entity" → "Source Company"
10. Improved error logging — warnings for unparseable dates and knock-off read failures
11. Hardened SQL input validation with whitelist for prefix, doctype, and date params
12. Config file gracefully ignores unknown keys (forward-compat)
13. Bundled customized FastReport (.fr3) for the consolidated 12-Month Customer Statement of Account grouped by Company Category — see User Guide → Database Prerequisites for import steps
14. Removed legacy CustomTkinter UI files (ui_app.py, tab_settings.py, tab_entity.py)

Release Build 1 – 20 Mar 2026
01. Initial release — AR document sync (IV, DN, CN, CT, PM, CF)
02. Multi-currency support with auto-creation (currency, GL account, payment method)
03. Customer master data sync with category mapping
04. Skip existing / Purge & Re-sync modes
05. Opening balance support (SystemConversionDate handling)
06. Tax code validation (SST/GST)
07. Category Mapping tab with filter, pagination, and batch operations
08. Unmapped customer filtering (skip customers without category assignment)
09. Preview / dry-run mode with record counts
10. Purge comparison preview (changed, new, deleted documents)
11. Date range filtering for sync operations
