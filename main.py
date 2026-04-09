"""Entry point for SQL Account Consolidation Sync Tool."""

import sys
import os
import io
import datetime
import traceback

# PyInstaller --windowed builds have sys.stdout / sys.stderr = None.
# uvicorn (used by NiceGUI) calls sys.stdout.isatty() during logging setup
# and crashes with AttributeError. Substitute dummy text streams BEFORE any
# import that might pull in uvicorn (i.e. before importing nicegui).
# Reference: https://github.com/encode/uvicorn/issues/1908
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()


def _write_startup_error(exc_text: str):
    """Write a startup crash to disk so windowed-mode failures are visible.

    PyInstaller's --windowed bootloader detaches stderr, so any unhandled
    exception during startup is otherwise invisible to the user. This writes
    the traceback to startup_error.log next to the .exe (or next to main.py
    in dev mode) so support has something to read.
    """
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        err_path = os.path.join(base, 'startup_error.log')
        with open(err_path, 'w', encoding='utf-8') as f:
            f.write(f"=== Startup error at {datetime.datetime.now()} ===\n")
            f.write(f"sys.executable = {sys.executable}\n")
            f.write(f"sys.frozen = {getattr(sys, 'frozen', False)}\n")
            f.write(f"sys._MEIPASS = {getattr(sys, '_MEIPASS', '<not set>')}\n")
            f.write(f"cwd = {os.getcwd()}\n\n")
            f.write(exc_text)
    except Exception:
        pass


def main():
    try:
        from logger import cleanup_old_logs
        cleanup_old_logs()

        # Set AppUserModelID so Windows taskbar shows our icon
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "eStream.SQLAccConsolSync")
        except Exception:
            pass

        from nicegui import ui
        from nicegui_app import create_app
        from version import APP_NAME, APP_VERSION

        create_app()

        # Resolve icon path
        if getattr(sys, 'frozen', False):
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_path, 'icon.png')
        if not os.path.exists(icon_path):
            icon_path = None

        ui.run(
            title=f'{APP_NAME} v{APP_VERSION}',
            port=0,          # Random free port
            reload=False,    # Required for PyInstaller
            show=True,       # Auto-open browser
            favicon=icon_path,
        )
    except Exception:
        error_detail = traceback.format_exc()
        _write_startup_error(error_detail)
        print(error_detail, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
