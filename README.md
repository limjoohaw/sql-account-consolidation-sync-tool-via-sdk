# SQL Account Consolidation Sync Tool

A desktop tool that extracts AR (Accounts Receivable) transactions from multiple source SQL Account databases and consolidates them into a single database for unified Statement of Account group by company category reporting.

Built for Windows with SQL Account SDK (COM).

## Quick Start

**Prerequisites:** Windows 10+, Python 3.11+, Firebird 3.0+, SQL Account 5.2025.1045.882+

```bash
pip install -r requirements.txt
python main.py
```

Or run the compiled version: `C:\eStream\Utilities\SQLAccConsolSync\SQLAccConsolSync.exe`

## Documentation

- **[User Guide](docs/user-guide.md)** — Full setup and usage instructions
- **[Changelog](CHANGELOG.md)** — Version history

## What It Does

- Syncs AR documents (IV, DN, CN, CT, PM, CF) from ~25 source databases into one consolidation database
- Auto-creates currencies, GL accounts, and payment methods
- Multi-currency support with ISO code standardization
- Skip existing (incremental) or Purge & Re-sync modes
- SST/GST tax code validation
- Opening balance support

## Architecture

**Dual data access:** reads via Firebird (`fdb` driver) for speed, writes via SQL Account SDK (COM) for business logic validation.

```
Source DBs (Firebird) → source_reader.py → transformer.py → consol_writer.py → Consolidation DB
```

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.
