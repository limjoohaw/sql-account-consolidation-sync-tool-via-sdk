# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# NiceGUI ships hundreds of static files (Quasar, Vue, Tailwind, fonts) and
# pulls in many dynamically-imported deps (uvicorn, fastapi, websockets,
# watchfiles, starlette). PyInstaller's static analyzer can't see them, so
# we must explicitly collect everything or the windowed exe crashes silently
# the moment NiceGUI tries to serve its first page.
nicegui_datas, nicegui_binaries, nicegui_hiddenimports = collect_all('nicegui')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=nicegui_binaries,
    datas=[
        ('icon.ico', '.'),
        ('icon.png', '.'),
        ('CHANGELOG.md', '.'),
        ('assets/1. Cust Statement 12 Mths 1 - Group.fr3', 'assets'),
    ] + nicegui_datas,
    hiddenimports=nicegui_hiddenimports + [
        'fdb',
        'win32com',
        'win32com.client',
        'pythoncom',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SQLAccConsolSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SQLAccConsolSync',
)
