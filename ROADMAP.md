# Roadmap

Project tracking for **SQL Consol Sync** (`SQLAccConsolSync.exe`) — SQL Account Consolidation Sync Tool.

**Status tags:** `[ ]` Planned | `[x]` Completed | `[!]` Known Bug

---

## Planned Enhancements

### High Priority

- [x] **App logo / icon**
  - `icon.png` (source 2583x2499 RGBA) → `icon.ico` (multi-size: 16–256px)
  - Applied via `self.iconbitmap()` in `ui_app.py`, with PyInstaller `_MEIPASS` path resolution

- [x] **Full user manual guide**
  - Create `USER_GUIDE.md` covering: installation, configuration, first-time setup, recurring sync workflow, Purge & Re-sync, troubleshooting
  - Include screenshots where helpful

- [ ] **User guide screenshots**
  - Capture and save to `docs/images/` (referenced from `docs/user-guide.md`):
  - [ ] `setup-tab.png` — Setup tab showing Consolidation DB config (left) + Source Companies grid (right)
  - [ ] `add-company-dialog.png` — "+ Add Company" dialog with FDB connection fields and auto-detected Company Info
  - [ ] `categories-tab.png` — Categories tab with customer list and searchable category dropdowns
  - [ ] `sync-tab.png` — Sync tab with multi-select source companies, modules, date range, and sync mode
  - [ ] `purge-re-sync-preview.png` — Purge & Re-sync comparison preview (changed/new/deleted)
  - [ ] `sync-log-output.png` — Sync Log panel showing progress and results

- [x] **Compile to .exe**
  - PyInstaller 6.x+ `--onedir --windowed` mode
  - .exe name: `SQLAccConsolSync.exe`, install to `C:\eStream\Utilities\SQLAccConsolSync\`
  - Bundles: Python runtime, fdb, pywin32, NiceGUI (full asset tree via `collect_all`), icon.ico, icon.png, CHANGELOG.md, `assets/1. Cust Statement 12 Mths 1 - Group.fr3`
  - `config.json`, `logs/`, and (on crash) `startup_error.log` created next to .exe at runtime (not inside `_internal/`)
  - Build: `pyinstaller SQLAccConsolSync.spec --clean --noconfirm` (see README for full instructions and the Troubleshooting table for known PyInstaller + NiceGUI gotchas)

### Medium Priority

- [x] **Log file auto-cleanup**
  - On app startup, keeps last 50 log files, deletes the rest (sorted by modification time)
  - `cleanup_old_logs()` in `logger.py`, called from `main.py`

### Low Priority

- [ ] **Source code & credential hardening**
  - **Background:** PyInstaller bundles Python bytecode (`.pyc`) inside `_internal/PYZ-00.pyz`. Anyone with file-system access to the install directory can extract it in ~5 minutes using free tools (`pyinstxtractor` + `uncompyle6` / `pycdc`) and recover ~95% of the original Python source. Third-party packages (NiceGUI, fdb, etc.) ship as plain `.py` files and have zero protection.
  - **Realistic risk assessment:**
    - The codebase has no API keys, no proprietary algorithms, no DRM logic — the value is in domain knowledge + ongoing support, not in any single function. Source theft has limited blast radius.
    - **The single highest-value target is `config.json`**, which sits next to the `.exe` and stores Firebird/SQL Account credentials in cleartext after the user fills in the Setup tab. Anyone with read access to the install folder (IT staff, malware, ex-employee) can grab them as-is today.
  - **Recommended improvements (in order of ROI):**
    - [ ] **Encrypt `config.json` password fields with Windows DPAPI** (`win32crypt.CryptProtectData`). ~30 min change in `config.py`. Ties decryption to the Windows user account that wrote the file, so a copied `config.json` is unreadable elsewhere. **This is the single most valuable hardening step.**
    - [ ] **Bytecode obfuscation via PyArmor** (or similar). Wraps `.pyc` files with an additional encryption layer that breaks `uncompyle6`. Raises the reverse-engineering bar from "5 minutes for a script kiddie" to "a few hours for a competent reverse engineer." Trade-offs: commercial license cost, occasional runtime issues with PyInstaller bundles, antivirus false positives. Worth it only if there's a specific secret in the code worth protecting.
    - [ ] **Strings audit** — run `strings.exe` against the bundled exe and verify no hardcoded credentials, API endpoints, or sensitive comments leak in plain text. Add a pre-build check.
    - [ ] **License agreement / EULA in the installer** — Inno Setup `LicenseFile` directive. Legal protection complements the technical layer.
  - **Out of scope (unless requirements change):**
    - Rewriting sensitive logic in C/C++/Rust (massive effort, no clear payoff for this codebase)
    - Server-side feature gating (requires network connectivity, breaks the offline-friendly design)

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
