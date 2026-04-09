---
sidebar_position: 1
id: acc-consol-sync
title: Consolidation Sync Guide
description: A quick guide on consolidation sync tool for SQL Account via SDK
slug: /miscellaneous/acc-consol-sync
tags: ["Consolidation", "Sync", "AR", "SDK", "SQLAccConsolSync"]
---

**SQL Consol Sync** is a desktop tool that extracts AR (Accounts Receivable) transactions from multiple source SQL Account databases and upserts them into a single consolidation database for unified **Statement of Account** group by company category reporting.

**Key features:**

- Sync AR documents: Invoice (IV), Debit Note (DN), Credit Note (CN), Contra (CT), Payment (PM), Refund (CF)
- Auto-create currencies, GL accounts, and payment methods in consolidation DB
- Multi-currency support with ISOCODE standardization
- Customer master data sync with Company Category mapping
- Skip existing (incremental) or Purge & Re-sync modes
- Opening balance support (SystemConversionDate handling)
- SST/GST tax code validation
- Preview / dry-run before sync
- Date range filtering

## Requirement

- Windows 10 or above (64-bit preferable)
- Python 3.11+ (for source installation)
- Firebird Server 3.0+
- SQL Account Version 5.2025.1045.882+
- SQL Account SDK COM registered (installed with SQL Accounting)

:::caution
Source databases and the consolidation database must be on the **same SQL Account version**. Mismatched versions may cause SDK errors during sync.
:::

## Database Prerequisites

- If any source database has SST/GST enabled, the consolidation database must also have SST/GST started
- Consolidation database must have all required **tax codes and rates** pre-configured (e.g. `6%;8%` for SST/GST) — the sync validates tax code existence but does not auto-create them
- Supports both **local FDB files** and **SQL Connect Public Cloud FDB** (remote Firebird)

:::info[Cloud Database Access]
For SQL Connect Public Cloud access, request connection details from your service dealer:
- Company Name, Server (e.g. `fb5-pos.sql.com.my`), Username, Password, Database name
- Example: Server=`fb5-pos.sql.com.my`, Database=`abc-trading-sdn-bhd-demo-cloud`
:::

### Customer Statement of Account Report Format

The consolidation database requires a customized **FastReport (.fr3)** format to produce the consolidated **12-Month Customer Statement of Account grouped by Company Category**. This format is provided with the tool — download and import it into SQL Account once during setup.

**Download:** [1. Cust Statement 12 Mths 1 - Group.fr3](../assets/1.%20Cust%20Statement%2012%20Mths%201%20-%20Group.fr3)

**Import steps:**

01. Open SQL Account and log in to the **consolidation database**
01. Go to **Tools → Report Designer**
01. Click **Import** and select the downloaded `.fr3` file
01. Click **Open** to load the format
01. Save — the new format becomes available when running the Customer Statement of Account report

:::caution
Import this format only into the **consolidation database**, not the source databases. The format is built around the consolidated data structure and will not produce meaningful output on a regular SQL Account database.
:::

## Installation

01. Install on the SQL Account server PC (where Firebird and SQL Accounting are installed)

01. Download and extract the program files, or install `SQLAccConsolSync.exe` to `C:\eStream\Utilities\SQLAccConsolSync\`

01. For source installation:
    ```
    pip install -r requirements.txt
    python main.py
    ```

## One-Time Setup

The app uses a **3-tab layout**: **Setup** | **Categories** | **Sync**. First-time users land on the Setup tab automatically; returning users land on the Sync tab.

### Configure Consolidation Database

![setup-tab](images/setup-tab.png)
*(Screenshot pending)*

01. Open the **Setup** tab

01. On the left side under **Consolidation Database**, fill in the two configuration sections:

    **SQL Account Configuration (SDK)** — used for writing data via the SDK:
    - **DCF Path** — Path to `Default.DCF` file (e.g. `C:\eStream\SQLAccounting\Share\Default.DCF`)
    - **Database Name** — Database name as registered in SQL Accounting (filename only, e.g. `CONSOLSOA.FDB` — not full path)
    - **Login Username / Login Password** — SQL Account login credentials (default: `ADMIN` / `ADMIN`)

    **Direct Database Connection (Read)** — used for fast reads (categories, preview, comparison). Recommended but optional:
    - **FDB Path** — Full path to the consolidation `.FDB` file (e.g. `C:\eStream\SQLAccounting\DB\CONSOLSOA.FDB`)
    - **Server Address** — Firebird server (default: `localhost`)
    - **Database Username / Database Password** — Firebird login (default: `SYSDBA` / `masterkey`)

01. Click **Test Connection**. The test runs in **two phases**:
    - **Phase 1** — SDK login + `SY_PROFILE` query to confirm SQL Account credentials
    - **Phase 2** — Firebird direct connection (only if FDB Path is filled in)

    Possible outcomes:
    - **Green** — both phases succeeded
    - **Yellow** — SDK works but FDB Path is blank or the direct connection failed (the app will still run but with slower reads)
    - **Red** — SDK login failed; check credentials and DCF/Database Name

01. Click **Save**

### Add Source Companies

On the **Setup** tab, the right-side card titled **Source Companies** holds the list of source databases.

01. Click **+ Add Company** to open the Add dialog

01. Fill in the source company details:

    **Direct Database Connection (Read)**:
    - **FDB Path** — Full path to the source company's `.FDB` file (e.g. `C:\eStream\SQLAccounting\DB\ACC-0001.FDB`)
    - **Server Address** — Firebird server (default: `localhost`)
    - **Database Username / Database Password** — Firebird login (default: `SYSDBA` / `masterkey`)

01. Click **Test Connection** in the dialog. If successful, the **Company Info** section auto-fills (read-only) from `SY_PROFILE`:
    - **Company Name** — from `SY_PROFILE.COMPANYNAME`
    - **Remark** — from `SY_PROFILE.REMARK`
    - **Prefix (ALIAS)** — from `SY_PROFILE.ALIAS`, used as the document number prefix in the consolidation DB

01. Under **Transformer**, set **Code Prefix to Remove** — the prefix to strip from source customer codes before re-prefixing with the company alias (e.g. `300-` if the source customer codes look like `300-A0001`). The dialog auto-detects this from a sample customer code if possible.

01. Click **Save** — the company appears in the Source Companies grid

01. Repeat for each source company

:::info[Company Prefix]
The company prefix (used to prefix document numbers in the consolidation DB) is read from `SY_PROFILE.ALIAS` in the source database. Make sure each source company has a **unique Company Alias** set in SQL Accounting before adding it here.
:::

:::tip
Use the pencil icon in the grid to edit a source company, or the trash icon to remove it. You can also double-click any row to open the edit dialog.
:::

### Assign Company Categories

![categories-tab](images/categories-tab.png)
*(Screenshot pending)*

01. Open the **Categories** tab

01. Select a source company from the **Source** dropdown and click **Load Customers**. Categories from the consolidation database are auto-loaded alongside the customer list. Use **Refresh Categories** to reload them after creating new categories in SQL Account.

01. For each customer, assign a **Company Category** from the dropdown in the Category column. The dropdown supports type-ahead search.

01. To assign the same category to many customers at once, use **Bulk Assign**:
    - Tick the rows you want to update (use column filters first to narrow the list)
    - Pick a category from the **Bulk Assign** dropdown
    - Click **Apply to Checked**

01. Use **Tick All** / **Un-tick All** to batch-select rows. These only affect rows currently visible after filtering.

01. Click **Save Mapping** to persist the category assignments

:::warning[Important]
Only customers with a category assigned will be synced. Unmapped customers are silently skipped during sync (their AR documents are also skipped). Company Categories must already exist in the consolidation database — create them in SQL Account under **Tools > Maintain Company Category** before assigning mappings here.
:::

## Recurring Sync

### Sync Tab

![sync-tab](images/sync-tab.png)
*(Screenshot pending)*

01. Open the **Sync** tab (the default tab for returning users — first-time users land on Setup until the Consolidation DB is configured)

01. **Source** — select source companies from the multi-select dropdown. The selection is **remembered between sessions**.

01. **Data** — select the data modules to sync from the multi-select dropdown. Modules are individual checkboxes:
    - **Customer** — customer master records
    - **IV** (Invoice), **DN** (Debit Note), **CN** (Credit Note), **CT** (Contra), **PM** (Payment), **CF** (Refund) — AR documents

01. **Date** — set the date range filter (optional, on by default):
    - **Date From** — defaults to the earliest `last_synced` timestamp across selected source companies
    - **Date To** — defaults to today
    - Untick the checkbox to disable date filtering entirely
    - Date From must be **on or before** Date To, otherwise the sync is rejected with a warning

01. **Mode** — choose sync mode:
    - **Skip existing** (default, recommended) — only imports new documents; skips documents that already exist in the consolidation DB
    - **Purge & Re-sync** — deletes all documents for the selected source companies within the date range, then re-imports fresh

01. Click **Preview** to see record counts (dry run, no data written). In Purge & Re-sync mode, Preview also shows a comparison diff (new / changed / deleted documents).

01. Click **Start Sync** to begin the actual sync. A confirmation dialog will appear before proceeding.

01. Monitor progress in the **Sync Log** on the right side. The log shows per-module status, errors, and total duration. Use **Export** to save the log to a `.log` file.

    ![sync-log-output](images/sync-log-output.png)
    *(Screenshot pending)*

01. Click **Cancel** to stop a running sync (current document finishes, then sync stops cleanly)

:::caution
Always **back up the consolidation database** before running a sync, especially in Purge & Re-sync mode.
:::

### Import Order

The sync enforces this import order to respect document dependencies:

**Import:** IV → DN → CN → CT → PM → CF

**Purge (reverse):** CF → PM → CN → CT → DN → IV

### Purge & Re-sync Mode

![purge-re-sync-preview](images/purge-re-sync-preview.png)

Use this mode when:
- Source data has been corrected or modified
- You need to re-import documents with updated amounts or details
- Documents were imported incorrectly

How it works:
- Deletes existing documents in **reverse order** (CF → PM → CN → CT → DN → IV)
- SQL Account automatically un-knock-offs related documents on delete
- Re-imports all documents fresh in forward order
- A comparison preview shows changed, new, and deleted documents before proceeding

:::warning[Purge Confirmation]
The purge confirmation dialog uses a **reverse question**: "Do you want to CANCEL the operation?" — clicking **Yes** cancels (safe default), clicking **No** proceeds with the purge.
:::

## Data Transformation Reference

The sync reads data from source databases via Firebird, transforms it to fit the consolidation database, and writes via the SQL Account SDK:

```
Source DBs (Firebird read) → Transformer → Consolidation DB (SDK write)
```

### Overview

| Module | Type | Auto-Created? | Key Transformation |
|--------|------|---------------|-------------------|
| Company Category | Master | No (must pre-exist in consol DB) | From Categories tab |
| Customer | Master | Upsert (create or update) | Code prefix swap, category reassignment |
| Currency | Master | Auto-create if missing | Standardized to ISO code |
| GL Account | Master | Auto-create if missing | JOURNAL-ISOCODE format (e.g. `BANK-USD`) |
| Payment Method | Master | Auto-created by GL Account | Linked to GL Account with currency |
| Invoice (IV) | Transaction | Insert only (skip if exists) | Doc no prefixed, GL account replaced |
| Debit Note (DN) | Transaction | Insert only (skip if exists) | Same as Invoice |
| Credit Note (CN) | Transaction | Insert only (skip if exists) | Same as Invoice + knock-offs |
| Contra (CT) | Transaction | Insert only (skip if exists) | Header + knock-offs only |
| Payment (PM) | Transaction | Insert only (skip if exists) | Payment method mapped + knock-offs |
| Refund (CF) | Transaction | Insert only (skip if exists) | Payment method mapped + knock-offs |

### Master Data

#### Company Category

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Code | Categories tab | From user assignment in Categories tab | `COMPANYCATEGORY.CODE` |
| Description | Categories tab | Same as Code | `COMPANYCATEGORY.DESCRIPTION` |

:::info
Company Categories must already exist in the consolidation database. The sync creates them if missing based on Categories tab assignments, but the categories should be pre-configured in SQL Account under **Tools > Maintain Company Category**.
:::

#### Customer

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Customer Code | `AR_CUSTOMER.CODE` | Strips source prefix (e.g. `300-`), prepends company alias (e.g. `A1-`). Example: `300-A0001` → `A1-A0001`. Max 10 characters. | `AR_CUSTOMER.CODE` |
| Company Name | `AR_CUSTOMER.COMPANYNAME` | Passed through | `AR_CUSTOMER.COMPANYNAME` |
| Company Name 2 | `SY_PROFILE.COMPANYNAME` | Set to the source company's name (identifies which source company the customer belongs to) | `AR_CUSTOMER.COMPANYNAME2` |
| Company Category | `AR_CUSTOMER.COMPANYCATEGORY` | **Replaced** with the category assigned in the Categories tab (looked up by original customer code) | `AR_CUSTOMER.COMPANYCATEGORY` |
| Currency | `AR_CUSTOMER.CURRENCYCODE` | Mapped from source currency code to ISO code (e.g. `aud` → `AUD`). Home currency (`----`) unchanged. | `AR_CUSTOMER.CURRENCYCODE` |
| Contact Person | `AR_CUSTOMERBRANCH.ATTENTION` | Passed through | `cdsBranch.ATTENTION` |
| Phone | `AR_CUSTOMERBRANCH.PHONE1` | Passed through | `cdsBranch.PHONE1` |
| Email | `AR_CUSTOMERBRANCH.EMAIL` | Passed through | `cdsBranch.EMAIL` |
| Address 1–4 | `AR_CUSTOMERBRANCH.ADDRESS1–4` | Passed through | `cdsBranch.ADDRESS1–4` |
| Postcode | `AR_CUSTOMERBRANCH.POSTCODE` | Passed through | `cdsBranch.POSTCODE` |

:::info[Create vs Update]
- **New customer:** All fields above are written, including billing branch details.
- **Existing customer:** Only Company Name, Company Name 2, and Company Category are updated. Branch/billing details are **not** overwritten.
:::

#### Currency

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Code | `CURRENCY.CODE` | Replaced with ISO code (e.g. source `aud` → consol `AUD`) | `CURRENCY.CODE` |
| Description | `CURRENCY.DESCRIPTION` | Replaced with ISO 4217 standard description | `CURRENCY.DESCRIPTION` |
| ISO Code | `CURRENCY.ISOCODE` | Passed through | `CURRENCY.ISOCODE` |
| Symbol | `CURRENCY.SYMBOL` | Replaced with ISO code | `CURRENCY.SYMBOL` |

:::info
Home currency (`CODE = "----"`) is skipped — it already exists in every SQL Account database. Only foreign currencies are auto-created when missing.
:::

#### GL Account & Payment Method

GL accounts and payment methods are auto-created based on source payment methods. Each unique journal type + currency combination creates one GL account and one payment method.

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| GL Code | `PMMETHOD.JOURNAL` + `CURRENCY.ISOCODE` | Combined as `JOURNAL-ISOCODE` (e.g. `BANK-USD`, `CASH-MYR`) | `GL_ACC.CODE` |
| Description | (derived) | Auto-generated from journal type and currency | `GL_ACC.DESCRIPTION` |
| Account Type | (derived) | Always `CA` (Current Asset) | `GL_ACC.ACCTYPE` |
| Special Type | `PMMETHOD.JOURNAL` | `BANK` → `BA`, `CASH` → `CH` | `GL_ACC.SPECIALACCTYPE` |
| PM Currency | `CURRENCY.ISOCODE` | Assigned to auto-created payment method. Home currency uses `----`. | `PMMETHOD.CURRENCYCODE` |

:::info
Creating a GL Account with bank/cash type in SQL Account **automatically creates a matching Payment Method**. The sync then assigns the correct currency to that payment method.
:::

### Transaction Documents

#### Invoice / Debit Note / Credit Note (IV, DN, CN)

These three document types share the same field structure with header + detail lines.

**Header Fields:**

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Customer Code | `AR_IV.CODE` | Same as Customer Code transformation above | `MainDataSet.CODE` |
| Document No | `AR_IV.DOCNO` | Prepends company alias (e.g. `INV-1001` → `A1-INV-1001`) | `MainDataSet.DOCNO` |
| Document Date | `AR_IV.DOCDATE` | Converted to `dd/mm/yyyy` format | `MainDataSet.DOCDATE` |
| Post Date | `AR_IV.POSTDATE` | Converted to `dd/mm/yyyy` format | `MainDataSet.POSTDATE` |
| Description | `AR_IV.DESCRIPTION` | Passed through | `MainDataSet.DESCRIPTION` |
| Currency | `AR_IV.CURRENCYCODE` | Mapped from source code to ISO code | `MainDataSet.CURRENCYCODE` |
| Currency Rate | `AR_IV.CURRENCYRATE` | Passed through | `MainDataSet.CURRENCYRATE` |
| Doc Amount | `AR_IV.DOCAMT` | Passed through (used for opening balance only) | `MainDataSet.DOCAMT` |
| Local Doc Amount | `AR_IV.LOCALDOCAMT` | Passed through (used for opening balance only) | `MainDataSet.LOCALDOCAMT` |

**Detail Line Fields (per line item):**

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Sequence | `AR_IVDTL.SEQ` | Re-sequenced from 1 | `cdsDocDetail.SEQ` |
| GL Account | `AR_IVDTL.ACCOUNT` | **Replaced** with consol DB default GL account (IV/DN → Sales Account, CN → Sales Return Account) | `cdsDocDetail.ACCOUNT` |
| Description | `AR_IVDTL.ACCOUNT` + `AR_IVDTL.DESCRIPTION` | Concatenated as `ACCOUNT \|\| DESCRIPTION` (preserves source GL code for audit trail) | `cdsDocDetail.DESCRIPTION` |
| Tax Code | `AR_IVDTL.TAX` | Passed through | `cdsDocDetail.TAX` |
| Tax Rate | `AR_IVDTL.TAXRATE` | Passed through | `cdsDocDetail.TAXRATE` |
| Tax Inclusive | `AR_IVDTL.TAXINCLUSIVE` | Passed through (special SDK handling applied automatically) | `cdsDocDetail.TAXINCLUSIVE` |
| Amount | `AR_IVDTL.AMOUNT` | Passed through | `cdsDocDetail.AMOUNT` |
| Tax Amount | `AR_IVDTL.TAXAMT` | Passed through | `cdsDocDetail.TAXAMT` |
| Exempted Tax Rate | `AR_IVDTL.EXEMPTED_TAXRATE` | Passed through | `cdsDocDetail.EXEMPTED_TAXRATE` |
| Exempted Tax Amount | `AR_IVDTL.EXEMPTED_TAXAMT` | Passed through | `cdsDocDetail.EXEMPTED_TAXAMT` |

**Knock-Off Fields (Credit Note only):**

Credit Notes can knock off (offset) Invoices and Debit Notes.

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Target Doc Type | `AR_KNOCKOFF.TODOCTYPE` | Passed through (`IV` or `DN`) | `cdsKnockOff.DocType` |
| Target Doc No | Resolved from `AR_IV.DOCNO` or `AR_DN.DOCNO` | Prepends company alias | `cdsKnockOff.DocNo` |
| Knock-Off Amount | `AR_KNOCKOFF.KOAMT` | Passed through (document currency) | `cdsKnockOff.KOAmt` |
| Local KO Amount | `AR_KNOCKOFF.LOCALKOAMT` | Passed through (home currency) | `cdsKnockOff.LocalKOAmt` |
| Actual Local KO Amount | `AR_KNOCKOFF.ACTUALLOCALKOAMT` | Passed through (original invoice rate) | `cdsKnockOff.ActualLocalKOAmt` |
| Gain/Loss | `AR_KNOCKOFF.GAINLOSS` | Passed through (realized exchange gain/loss) | `cdsKnockOff.GainLoss` |

#### Contra (CT)

Contra documents have header + knock-offs only (no detail lines). Knocks off Invoices and Debit Notes.

**Header Fields:**

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Customer Code | `AR_CT.CODE` | Same as Customer Code transformation | `MainDataSet.CODE` |
| Document No | `AR_CT.DOCNO` | Prepends company alias | `MainDataSet.DOCNO` |
| Document Date | `AR_CT.DOCDATE` | Converted to `dd/mm/yyyy` | `MainDataSet.DOCDATE` |
| Post Date | `AR_CT.POSTDATE` | Converted to `dd/mm/yyyy` | `MainDataSet.POSTDATE` |
| Description | `AR_CT.DESCRIPTION` | Passed through | `MainDataSet.DESCRIPTION` |
| Currency | `AR_CT.CURRENCYCODE` | Mapped to ISO code | `MainDataSet.CURRENCYCODE` |
| Currency Rate | `AR_CT.CURRENCYRATE` | Passed through | `MainDataSet.CURRENCYRATE` |
| Doc Amount | `AR_CT.DOCAMT` | Passed through | `MainDataSet.DOCAMT` |

**Knock-Off Fields:** Same as Credit Note knock-offs above (targets IV/DN).

#### Payment (PM)

Payment documents have header + payment-specific fields + knock-offs (no detail lines). Knocks off Invoices and Debit Notes.

**Header Fields:**

| Field | Source DB | Transformation | Consol DB |
|-------|----------|----------------|-----------|
| Customer Code | `AR_PM.CODE` | Same as Customer Code transformation | `MainDataSet.CODE` |
| Document No | `AR_PM.DOCNO` | Prepends company alias | `MainDataSet.DOCNO` |
| Document Date | `AR_PM.DOCDATE` | Converted to `dd/mm/yyyy` | `MainDataSet.DOCDATE` |
| Post Date | `AR_PM.POSTDATE` | Converted to `dd/mm/yyyy` | `MainDataSet.POSTDATE` |
| Description | `AR_PM.DESCRIPTION` | Passed through | `MainDataSet.DESCRIPTION` |
| Currency | `AR_PM.CURRENCYCODE` | Mapped to ISO code | `MainDataSet.CURRENCYCODE` |
| Currency Rate | `AR_PM.CURRENCYRATE` | Passed through | `MainDataSet.CURRENCYRATE` |
| Doc Amount | `AR_PM.DOCAMT` | Passed through | `MainDataSet.DOCAMT` |
| Payment Method | `AR_PM.PAYMENTMETHOD` | Mapped from source code to `JOURNAL-ISOCODE` format (e.g. `CIMB-USD` → `BANK-USD`) | `MainDataSet.PAYMENTMETHOD` |
| Cheque Number | `AR_PM.CHEQUENUMBER` | Passed through | `MainDataSet.CHEQUENUMBER` |

**Knock-Off Fields:** Same as Credit Note knock-offs above (targets IV/DN).

#### Customer Refund (CF)

Same structure as Payment, but knock-offs target **Credit Notes and Payments** (not IV/DN).

**Header Fields:** Same as Payment above (using `AR_CF` table).

**Knock-Off Fields:** Same knock-off structure, but targets `CN` and `PM` documents instead of `IV`/`DN`.

### Special Handling

:::info[Opening Balance Documents]
Documents dated before the consolidation database's **System Conversion Date** are treated as opening balances — only the header amounts (`DOCAMT`, `LOCALDOCAMT`) are saved, with **no detail lines**. This is a SQL Account SDK requirement.
:::

:::info[Tax Inclusive Lines]
Detail lines with tax-inclusive amounts are handled automatically during import. The sync applies special SDK techniques to preserve the exact amounts without SDK auto-recalculation.
:::

:::info[Unmapped Customers]
Only customers with a Company Category assigned in the Categories tab are synced. All documents belonging to unmapped customers are silently skipped. Check the sync log for skipped customer details.
:::

:::caution[Customer Code Length Limit]
SQL Account enforces a **10-character maximum** for customer codes. After transformation (stripping prefix + prepending company alias), the resulting code must not exceed 10 characters. The sync will report an error if this limit is exceeded.
:::

## FAQ

**Q: Why are some customers not being synced?**

Only customers with a Company Category assigned in the Categories tab are synced. Unmapped customers are silently skipped. Check the Categories tab and assign categories to the missing customers.

**Q: I get a "Tax code not found" error. What should I do?**

The sync validates that all tax codes used in source documents exist and are active in the consolidation database. Go to SQL Account > SST/GST or Tools > Maintain Tax in the consolidation database and create or enable the missing tax codes.

**Q: Can I sync from SQL Connect Public Cloud databases?**

Yes. Enter the cloud Firebird server address and database name in the **+ Add Company** dialog on the Setup tab. Request connection details from your SQL service dealer.

**Q: What happens if the sync is interrupted?**

Documents that were already synced remain in the consolidation database. You can re-run the sync — in Skip existing mode, already-imported documents will be skipped. In Purge & Re-sync mode, all documents will be deleted and re-imported.

**Q: Why do I see "SDK session locked" errors?**

The SDK COM is a singleton — only one session can be active at a time. Ensure SQL Accounting is not open on the same PC, and that no other sync process is running. The tool automatically releases the SDK license on exit.

**Q: How are currencies handled across different source companies?**

Source databases may have user-defined currency codes (e.g. `aud`). The consolidation database standardizes to ISO currency codes (e.g. `AUD`). Missing currencies are auto-created during sync.

**Q: What are opening balance documents?**

Documents with a date before the System Conversion Date have header amounts but no detail lines. The sync handles these correctly — importing only the header with `DOCAMT`/`LOCALDOCAMT`, without creating detail lines.

## Program History

See [CHANGELOG.md](https://github.com/limjoohaw/sql-account-consolidation-sync-tool-via-sdk/blob/master/CHANGELOG.md) for the full version history.
