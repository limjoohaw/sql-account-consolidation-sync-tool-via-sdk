"""Entry point for SQL Account Consolidation Sync Tool."""

import sys
import traceback


def main():
    try:
        from ui_app import App
        app = App()
        app.mainloop()
    except Exception as e:
        error_detail = traceback.format_exc()
        try:
            from tkinter import messagebox
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Startup Error",
                f"Failed to start application:\n\n{e}\n\n"
                f"Please check that all dependencies are installed "
                f"and config.json is valid."
            )
            root.destroy()
        except Exception:
            pass
        print(error_detail, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
