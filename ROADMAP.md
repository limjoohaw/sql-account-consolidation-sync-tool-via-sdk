# Roadmap

Project tracking for **SQL Consol Sync** (`SQLAccConsolSync.exe`) — SQL Account Consolidation Sync Tool.

**Status tags:** `[ ]` Planned | `[x]` Completed | `[!]` Known Bug

---

## Planned Enhancements

### High Priority

- [ ] **App logo / icon**
  - Design or source an icon for the tool (window icon + taskbar + .exe icon)
  - Apply via `self.iconbitmap()` or `self.wm_iconphoto()` in CustomTkinter

- [x] **Full user manual guide**
  - Create `USER_GUIDE.md` covering: installation, configuration, first-time setup, recurring sync workflow, Purge & Re-sync, troubleshooting
  - Include screenshots where helpful

- [ ] **User guide screenshots**
  - Capture and save to `docs/images/`:
  - [ ] `settings-tab.png` — Settings tab with consol DB connection fields
  - [ ] `entity-manager-tab.png` — Entity Manager tab with entity list
  - [ ] `add-entity-dialog.png` — Add Entity dialog with fields filled in
  - [ ] `category-mapping-tab.png` — Category Mapping tab with customer list and category dropdowns
  - [ ] `sync-dashboard-tab.png` — Sync Dashboard with entities, modules, date range, and mode selection
  - [ ] `purge-re-sync-preview.png` — Purge & Re-sync comparison preview (changed/new/deleted)
  - [ ] `sync-log-output.png` — Sync log panel showing progress and results

- [ ] **Compile to .exe**
  - Use **PyInstaller** (v6.x+) to compile to standalone Windows executable
  - .exe name: `SQLAccConsolSync.exe`
  - Shortcut name: `SQL Consol Sync`
  - Default install location: `C:\eStream\Utilities\SQLAccConsolSync\`
  - Must bundle: Python runtime, fdb, pywin32, customtkinter, all project files
  - **Build method:** Use `--onedir` mode (not `--onefile`) — faster startup, easier to debug/update
  - **Build files to create:** `SQLAccConsolSync.spec` (build config) + `build.bat` (one-click build script)
  - **Spec file** controls all build settings (hidden imports, data files, icon, version info) — version it in source control
  - **Version stamping:** PyInstaller can read `version.py` to embed version info in .exe properties
  - **Quick build command:** `pyinstaller SQLAccConsolSync.spec`
  - **First-time setup:** `pip install pyinstaller` then create .spec via `pyinstaller --onedir --windowed --name "SQLAccConsolSync" --icon=icon.ico main.py`
  - **Testing:** Test on clean Windows machine without Python installed
  - **Future:** Consider code signing certificate to avoid Windows SmartScreen warnings

### Medium Priority

- [ ] **Log file auto-cleanup**
  - Sync logs accumulate in `logs/` folder with no cleanup
  - Auto-delete old logs on app startup (e.g. keep last 30 days or last 50 files)
  - Optionally add "Clear Logs" button in Settings or Sync Dashboard

### Low Priority

- [ ] **Licensing & activation system**
  - Subscription model with key-based activation tied to Machine ID or SQL Account Dongle ID
  - For commercial distribution of the tool

---

## Testing To-Do

- [x] **End-to-end test with SST + multi-currency data**
  - Verify tax amounts (TAXAMT, EXEMPTED_TAXAMT) written correctly to consol DB
  - Verify foreign currency documents have correct CURRENCYCODE and CURRENCYRATE
  - Verify cross-currency knock-off fields (LocalKOAmt, ActualLocalKOAmt, GainLoss) match source
  - Verify auto-created GL accounts (BANK-USD etc.) and PMMETHOD currency assignments are correct

- [x] **Test Purge & Re-sync end-to-end**
  - Verify delete order CF → PM → CN → CT → DN → IV works correctly
  - Verify re-imported documents have correct knock-offs re-established
  - Verify comparison preview correctly identifies changed/new/deleted documents

---

## Known Bugs

_(none currently tracked)_

---

## Changelog

### 2026-03-21

- [x] **UI standardization across all tabs** — Consistent typography (FONT_SECTION labels with colons), grid layout (width=350 fields, sticky="w" labels), centered footer action buttons, white grid backgrounds (fg_color="white", height=300), FONT_CODE_SM for all grid data. Applied to: Sync Dashboard, Category Mapping, Entity Manager, Settings, Entity Dialog
- [x] **Inline style constants** — Replaced all inline hex colors/fonts with constants: CLR_DANGER, CLR_DANGER_HOVER, CLR_TEXT_MUTED, FONT_ICON, FONT_TOOLTIP
- [x] **Category Mapping improvements** — Set Checked changed from SearchableComboBox to CTkComboBox, "Refresh Categories" renamed to "Load Categories", Apply/Save Mapping moved to centered footer
- [x] **Entity Manager cleanup** — Removed redundant Select All/Unselect All buttons (header checkbox handles this), search bar width=350, Add Entity/Remove Selected moved to centered footer
- [x] **Comparison preview performance** — Replaced SDK COM reads with direct Firebird reads in `compare_documents()`, eliminating all SDK login/logout during Purge & Re-sync preview
- [x] **Master Data popup layout fix** — Minimum popup height of 180px so Select All/Deselect All/OK buttons are not cramped

### 2026-03-20

- [x] **Multi-currency transaction support** — Full pipeline: currency auto-creation (ISOCODE matching), customer CURRENCYCODE, document CURRENCYCODE/CURRENCYRATE on all 6 doc types, ISO 4217 description mapping
- [x] **Cross-currency knock-off fields** — Read/write LocalKOAmt, ActualLocalKOAmt, GainLoss on AR_KNOCKOFF for exchange rate gain/loss tracking
- [x] **GL account auto-creation** — For each JOURNAL-ISOCODE combo (e.g. BANK-USD), creates GL_ACC under _CA_ parent with SpecialAccType=BA/CH
- [x] **Payment method standardization** — PMMETHOD auto-created by SQL Account when GL_ACC created, then CurrencyCode assigned. Source PMMETHOD.CODE mapped to JOURNAL-ISOCODE format via pm_lookup
- [x] **SST tax fields** — TAXINCLUSIVE (boolean), TAXAMT, EXEMPTED_TAXRATE, EXEMPTED_TAXAMT read from source and written to consol DB detail lines
- [x] **Tax code validation** — Pre-sync check that all source tax codes exist and are active in consol DB (code-only, no rate comparison)
- [x] **Purge & Re-sync mode** — Delete all documents for entity in reverse order (CF→PM→CN→CT→DN→IV), then re-import fresh. Includes comparison preview and reverse confirmation dialog
- [x] **Category Mapping currency column** — Grid now shows Currency Code column for each customer
- [x] **Company Category active filter** — Only shows `ISACTIVE=TRUE` categories in dropdown
- [x] **Tab bar reordered** — Sync Dashboard → Category Mapping → Entity Manager → Settings
- [x] **Removed standalone Today/Clear buttons** — Date fields now only use the `...` popup which already has Today/Clear/Cancel
- [x] **Date filter defaults** — Checkbox defaults to checked; Date From = earliest last_synced of enabled entities; Date To = today

### 2026-03-12

- [x] **AR_CF (Customer Refund) module** — full pipeline support: read from source (`AR_CF`), transform, write via SDK (`AR_CF` BizObject). CF knocks off CN/PM only
- [x] **Sync Dashboard module popups** — replaced inline checkboxes with compact `...` popup buttons for Master Data and Transaction Data selection
- [x] **Master/Transaction data popups** — both popups now have Select All / Deselect All / OK buttons, extensible for future modules
- [x] **AR_CT (Contra) separate handler** — dedicated `insert_ar_contra()` with DOCAMT on header + knock-off via `cdsKnockOff`
- [x] **CN knock-off support** — CN now knocks off IV/DN using `cdsKnockOff` dataset, same pattern as PM
- [x] **Default GL accounts from consol DB** — IV/DN use `SalesAccount`, CN uses `SalesReturnAccount` from `SY_REGISTRY`
- [x] **Default payment method** — PM and CF use first `PMMETHOD WHERE JOURNAL='BANK'` from consol DB
- [x] **Detail description format** — consol DB detail shows `"OriginalGLAccount || OriginalDescription"` from source
- [x] **Date format fix** — SDK date fields use `.AsString` with `dd/mm/yyyy` string format
- [x] **Boolean field fix** — SDK boolean fields use `.value = True/False` instead of `.AsString = "T"/"F"`
- [x] **Filter cancelled transactions** — all doc type queries filter `WHERE CANCELLED=FALSE`
- [x] **Native tooltip** — replaced CTkToplevel tooltip with `tk.Toplevel` + 400ms show delay for reliable hover behavior
- [x] **CompanyName2 sync** — source entity's `SY_PROFILE.COMPANYNAME` written to `AR_CUSTOMER.COMPANYNAME2` in consol DB
