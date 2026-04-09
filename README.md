# SQL Account Consolidation Sync Tool

<p align="center">
  <img src="icon.png" alt="SQL Consol Sync" width="128">
</p>

A desktop tool that extracts AR (Accounts Receivable) transactions from multiple source SQL Account databases and consolidates them into a single database for unified Statement of Account grouped by Company Category reporting.

Built for Windows with SQL Account SDK (COM). The UI is web-based (NiceGUI) and opens automatically in the user's default browser at a local port.

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

## Build & Distribution

Compile the app into a standalone `.exe` and package it as a Windows installer. The output is a single `Setup_SQLAccConsolSync.exe` that users download, run, and install — **no Python needed** on the target PC.

### Build Tools

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ (3.14+ used for releases) | Runtime (bundled into .exe) |
| PyInstaller | 6.19+ | Compiles Python → standalone .exe |
| Inno Setup | 6.7+ | Creates Windows installer (setup wizard) |
| Pillow | 12.1+ | PNG → ICO icon conversion (one-time) |

### Step 1: Install Build Tools

```bash
pip install pyinstaller pillow
```

Download and install [Inno Setup 6](https://jrsoftware.org/isdl.php) (free, ~4 MB).

### Step 2: Convert Icon (one-time only)

Skip this if `icon.ico` already exists in the project root.

```bash
python -c "from PIL import Image; img = Image.open('icon.png'); img.save('icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
```

### Step 3: Compile .exe with PyInstaller

```bash
pyinstaller SQLAccConsolSync.spec
```

Or build from scratch (first time only — generates the `.spec` file):

```bash
pyinstaller --onedir --windowed --name "SQLAccConsolSync" --icon=icon.ico --add-data "icon.ico;." --add-data "icon.png;." --add-data "CHANGELOG.md;." --add-data "assets/1. Cust Statement 12 Mths 1 - Group.fr3;assets" main.py
```

Output in `dist/SQLAccConsolSync/`:

```
dist/SQLAccConsolSync/
├── SQLAccConsolSync.exe        ← Main executable
├── _internal/                  ← Python runtime & dependencies
│   ├── icon.ico
│   ├── icon.png
│   ├── CHANGELOG.md
│   ├── assets/
│   │   └── 1. Cust Statement 12 Mths 1 - Group.fr3
│   └── ...
├── config.json                 ← Created at runtime
└── logs/                       ← Created at runtime
```

### Step 4: Build Installer with Inno Setup

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Output: `installer_output/Setup_SQLAccConsolSync.exe` (~17 MB single file).

### Step 5: Distribute

Share `Setup_SQLAccConsolSync.exe` with users. They run it and get:

1. Setup wizard → Next → Next → Finish
2. Installs to `C:\eStream\Utilities\SQLAccConsolSync\`
3. Desktop shortcut with app icon
4. Start Menu entry
5. Proper uninstall via "Add/Remove Programs"

### Target PC Requirements

- Windows 10+ (64-bit)
- SQL Account 5.2025.1045.882+ (with SDK COM registered)
- Firebird Server 3.0+
- **No Python needed** — bundled in the `.exe`