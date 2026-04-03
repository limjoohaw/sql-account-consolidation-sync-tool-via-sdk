"""Entry point for SQL Account Consolidation Sync Tool."""

import sys
import os
import traceback


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
    except Exception as e:
        error_detail = traceback.format_exc()
        print(error_detail, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
