"""CustomTkinter UI for SQL Account Consolidation Sync Tool."""

import os
import sys
import calendar
import threading
import pythoncom
import fdb
import customtkinter as ctk
from datetime import date, datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from config import AppConfig, EntityConfig, ConsolDBConfig, load_config, save_config
from sync_engine import SyncEngine, IMPORT_ORDER, _format_duration
from logger import SyncLogger
from version import APP_NAME, APP_VERSION, APP_BUILD_NUMBER

ctk.set_appearance_mode("light")
ctk.set_default_color_theme(os.path.join(os.path.dirname(__file__), "purple_theme.json"))

# Brand colors (SQL Account indigo-purple palette)
CLR_PRIMARY = "#5B4FC7"       # indigo purple
CLR_SECONDARY = "#7B6FD4"     # lighter indigo (hover states)
CLR_ACCENT = "#8B7FE8"        # soft purple (action buttons)
CLR_BG_SEC = "#E8E4F8"        # very light lavender (headers, footer)
CLR_BG_HOVER = "#D5CFEF"      # light lavender (hover, unselected tabs)
CLR_DANGER = "#e74c3c"        # red (destructive actions)
CLR_DANGER_HOVER = "#c0392b"  # dark red (destructive hover)
CLR_TEXT_MUTED = "#aaaaaa"    # muted gray (summary/hint text)

# Typography
FONT_TITLE   = ("Arial", 16, "bold")    # Page/section titles
FONT_SECTION = ("Arial", 13, "bold")    # Section labels, table headers
FONT_BODY    = ("Arial", 12)            # Body text, field labels, summaries
FONT_CAPTION = ("Arial", 10)            # Footer, tooltips, small hints
FONT_CODE    = ("Consolas", 12)         # Log output, monospace data
FONT_CODE_SM = ("Consolas", 11)         # Customer codes, prefixes in grids
FONT_ICON    = ("Segoe UI", 12)         # Info icons
FONT_TOOLTIP = ("Segoe UI", 10)         # Tooltip text


class SearchableComboBox(ctk.CTkFrame):
    """A combobox-like widget with a searchable dropdown popup.

    API matches CTkComboBox: .get(), .set(value), .configure(values=...).
    """

    def __init__(self, master, values=None, width=250, placeholder="(none)", **kwargs):
        super().__init__(master, fg_color="transparent", width=width, **kwargs)
        self._values = values or []
        self._current = placeholder
        self._placeholder = placeholder
        self._popup = None
        self._width = width

        self._button = ctk.CTkButton(
            self, text=self._current, width=width, height=28,
            fg_color="white", text_color="gray10", border_width=1,
            border_color="gray60", hover_color="#f0f0f0",
            anchor="w", font=FONT_BODY,
            command=self._toggle_popup,
        )
        self._button.pack(fill="x")

    def get(self) -> str:
        return self._current

    def set(self, value: str):
        self._current = value
        display = value if value else self._placeholder
        self._button.configure(text=display)

    def configure(self, **kwargs):
        if "values" in kwargs:
            self._values = kwargs.pop("values")
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._button.configure(state="normal" if state != "disabled" else "disabled")
        if kwargs:
            super().configure(**kwargs)

    def cget(self, key):
        if key == "values":
            return self._values
        return super().cget(key)

    def _toggle_popup(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        self._open_popup()

    def _open_popup(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()

        self._popup = ctk.CTkToplevel(self)
        self._popup.wm_overrideredirect(True)
        self._popup.attributes("-topmost", True)
        self._popup.configure(fg_color="white")

        # Position below the button
        x = self._button.winfo_rootx()
        y = self._button.winfo_rooty() + self._button.winfo_height() + 2
        popup_w = max(self._width, 300)
        self._popup.geometry(f"{popup_w}x280+{x}+{y}")

        # Search entry
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_popup_items())
        search_entry = ctk.CTkEntry(
            self._popup, textvariable=self._search_var,
            placeholder_text="Type to search...", width=popup_w - 10, height=28,
        )
        search_entry.pack(padx=5, pady=(5, 2))
        search_entry.focus_set()

        # Scrollable list
        self._popup_scroll = ctk.CTkScrollableFrame(
            self._popup, fg_color="white", height=220,
        )
        self._popup_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        self._filter_popup_items()

        # Close on click outside
        self._popup.bind("<FocusOut>", self._on_popup_focus_out)
        search_entry.bind("<Escape>", lambda e: self._close_popup())

    def _filter_popup_items(self):
        if not self._popup or not self._popup.winfo_exists():
            return
        for w in self._popup_scroll.winfo_children():
            w.destroy()

        query = self._search_var.get().lower().strip()
        for val in self._values:
            if query and query not in val.lower():
                continue
            btn = ctk.CTkButton(
                self._popup_scroll, text=val, anchor="w", height=26,
                fg_color="white" if val != self._current else CLR_BG_SEC,
                text_color="gray10", hover_color=CLR_BG_HOVER,
                border_width=0, font=FONT_BODY,
                command=lambda v=val: self._select(v),
            )
            btn.pack(fill="x", padx=2, pady=1)

    def _select(self, value: str):
        self.set(value)
        self._close_popup()

    def _close_popup(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup = None

    def _on_popup_focus_out(self, event):
        if self._popup and self._popup.winfo_exists():
            # Check if focus moved to a child of the popup
            try:
                focused = self._popup.focus_get()
                if focused and (focused == self._popup or
                                str(focused).startswith(str(self._popup))):
                    return
            except KeyError:
                pass
            self._popup.after(150, self._check_and_close)

    def _check_and_close(self):
        if self._popup and self._popup.winfo_exists():
            try:
                focused = self._popup.focus_get()
                if focused and str(focused).startswith(str(self._popup)):
                    return
            except (KeyError, Exception):
                pass
            self._close_popup()


class App(ctk.CTk):
    def __init__(self):
        # Set AppUserModelID so Windows taskbar shows our icon, not Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("eStream.SQLAccConsolSync")

        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("950x700")
        self.minsize(800, 600)

        # Set window/taskbar icon (works in dev and PyInstaller bundle)
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_path, "icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        self.config = load_config()
        self.sync_engine = None
        self._sync_thread = None
        self._company_categories = []  # Cache for consol DB company categories
        self._ent_render_timer = None  # Debounce timer for entity search
        # (tooltip state managed per-icon via _NativeTooltip class)

        # Menu bar
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="What's New", command=self._show_whats_new)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menubar)

        # Footer status bar
        footer = ctk.CTkFrame(self, height=25, fg_color=CLR_BG_SEC, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        ctk.CTkLabel(footer, text=f"{APP_NAME} v{APP_VERSION} ({APP_BUILD_NUMBER})",
                      font=FONT_CAPTION, text_color="gray40"
                      ).pack(side="left", padx=10)

        # Tab view
        self.tabview = ctk.CTkTabview(self, anchor="nw")
        self.tabview.configure(
            segmented_button_selected_color=CLR_PRIMARY,
            segmented_button_selected_hover_color=CLR_SECONDARY,
            segmented_button_unselected_color=CLR_BG_SEC,
            segmented_button_unselected_hover_color=CLR_BG_HOVER,
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tabview.add("Sync")
        self.tabview.add("Category Mapping")
        self.tabview.add("Entity Manager")
        self.tabview.add("Settings")

        self._build_settings_tab()
        self._build_entity_tab()
        self._build_category_tab()
        self._build_sync_tab()

    # ==================================================================
    # SETTINGS TAB
    # ==================================================================
    def _build_settings_tab(self):
        tab = self.tabview.tab("Settings")

        frame = ctk.CTkFrame(tab)
        frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(frame, text="Consolidation Database", font=FONT_TITLE,
                      text_color=CLR_PRIMARY).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        row = 1

        # FDB Path (with tooltip)
        fdb_lbl_frame = ctk.CTkFrame(frame, fg_color="transparent")
        fdb_lbl_frame.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkLabel(fdb_lbl_frame, text="FDB Path:", font=FONT_SECTION).pack(side="left")
        self._create_info_icon(fdb_lbl_frame,
                               "Full path to the consolidation .FDB file\n"
                               "e.g. C:\\eStream\\SQLAccounting\\DB\\CONSOLSOA.FDB")
        self.consol_fb_path_var = ctk.StringVar(value=self.config.consol_db.fb_path)
        ctk.CTkEntry(frame, textvariable=self.consol_fb_path_var, width=350,
                      placeholder_text="e.g. C:\\eStream\\SQLAccounting\\DB\\CONSOLSOA.FDB").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)
        ctk.CTkButton(frame, text="...", width=40, fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY,
                       command=lambda: self._browse_file(self.consol_fb_path_var, [("FDB", "*.FDB")])).grid(
            row=row, column=2, padx=5, pady=5)
        row += 1

        # Firebird Host
        ctk.CTkLabel(frame, text="Firebird Host:", font=FONT_SECTION).grid(
            row=row, column=0, sticky="w", padx=10, pady=5)
        self.consol_fb_host_var = ctk.StringVar(value=self.config.consol_db.fb_host)
        ctk.CTkEntry(frame, textvariable=self.consol_fb_host_var, width=350,
                      placeholder_text="localhost (or server IP)").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # Firebird User
        ctk.CTkLabel(frame, text="Firebird User:", font=FONT_SECTION).grid(
            row=row, column=0, sticky="w", padx=10, pady=5)
        self.consol_fb_user_var = ctk.StringVar(value=self.config.consol_db.fb_user)
        ctk.CTkEntry(frame, textvariable=self.consol_fb_user_var, width=350,
                      placeholder_text="SYSDBA").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # Firebird Password
        ctk.CTkLabel(frame, text="Firebird Password:", font=FONT_SECTION).grid(
            row=row, column=0, sticky="w", padx=10, pady=5)
        self.consol_fb_pass_var = ctk.StringVar(value=self.config.consol_db.fb_password)
        ctk.CTkEntry(frame, textvariable=self.consol_fb_pass_var, width=350, show="*",
                      placeholder_text="masterkey").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # DCF Path (with tooltip)
        dcf_lbl_frame = ctk.CTkFrame(frame, fg_color="transparent")
        dcf_lbl_frame.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkLabel(dcf_lbl_frame, text="DCF Path:", font=FONT_SECTION).pack(side="left")
        self._create_info_icon(dcf_lbl_frame,
                               "SQL Account DCF file path\n"
                               "Used for SDK write operations during sync")
        self.consol_dcf_var = ctk.StringVar(value=self.config.consol_db.dcf_path)
        ctk.CTkEntry(frame, textvariable=self.consol_dcf_var, width=350,
                      placeholder_text="e.g. C:\\eStream\\SQLAccounting\\Share\\Default.DCF").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)
        ctk.CTkButton(frame, text="...", width=40, fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY,
                       command=lambda: self._browse_file(self.consol_dcf_var, [("DCF", "*.DCF")])).grid(
            row=row, column=2, padx=5, pady=5)
        row += 1

        # DB Name (with tooltip)
        db_lbl_frame = ctk.CTkFrame(frame, fg_color="transparent")
        db_lbl_frame.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkLabel(db_lbl_frame, text="DB Name:", font=FONT_SECTION).pack(side="left")
        self._create_info_icon(db_lbl_frame,
                               "Filename only (NOT full path)\n"
                               "Used for SDK write operations during sync")
        self.consol_db_var = ctk.StringVar(value=self.config.consol_db.db_name)
        ctk.CTkEntry(frame, textvariable=self.consol_db_var, width=350,
                      placeholder_text="Filename only, e.g. CONSOLSOA.FDB (NOT full path)").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # SQL Acc Username
        ctk.CTkLabel(frame, text="SQL Acc Username:", font=FONT_SECTION).grid(
            row=row, column=0, sticky="w", padx=10, pady=5)
        self.consol_user_var = ctk.StringVar(value=self.config.consol_db.username)
        ctk.CTkEntry(frame, textvariable=self.consol_user_var, width=350,
                      placeholder_text="ADMIN").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # SQL Acc Password
        ctk.CTkLabel(frame, text="SQL Acc Password:", font=FONT_SECTION).grid(
            row=row, column=0, sticky="w", padx=10, pady=5)
        self.consol_pass_var = ctk.StringVar(value=self.config.consol_db.password)
        ctk.CTkEntry(frame, textvariable=self.consol_pass_var, width=350, show="*",
                      placeholder_text="ADMIN").grid(
            row=row, column=1, sticky="w", padx=5, pady=5)

        # Action buttons (centered footer)
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(btn_frame, text="Test Connection", fg_color=CLR_ACCENT,
                       hover_color=CLR_SECONDARY,
                       command=self._test_consol_connection).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Save Settings", fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY,
                       command=self._save_settings).pack(side="left", padx=10)

    def _save_settings(self):
        self.config.consol_db = ConsolDBConfig(
            dcf_path=self.consol_dcf_var.get(),
            db_name=self.consol_db_var.get(),
            username=self.consol_user_var.get(),
            password=self.consol_pass_var.get(),
            fb_host=self.consol_fb_host_var.get(),
            fb_path=self.consol_fb_path_var.get(),
            fb_user=self.consol_fb_user_var.get(),
            fb_password=self.consol_fb_pass_var.get(),
        )
        save_config(self.config)
        messagebox.showinfo("Saved", "Consolidation DB settings saved.")

    def _test_consol_connection(self):
        """Test SDK login to the consolidation database."""
        dcf = self.consol_dcf_var.get().strip()
        db = self.consol_db_var.get().strip()
        user = self.consol_user_var.get().strip()
        pwd = self.consol_pass_var.get().strip()

        if not dcf or not db:
            messagebox.showwarning("Missing Fields", "Please fill in DCF Path and DB Name.")
            return

        try:
            import win32com.client
            app = win32com.client.Dispatch("SQLAcc.BizApp")

            # Logout existing session first (singleton)
            if app.IsLogin:
                app.Logout()

            app.Login(user, pwd, dcf, db)

            if not app.IsLogin:
                messagebox.showerror("Connection Failed",
                                     "Login failed. Please check your username/password.")
                return

            # Verify by running a simple query
            try:
                ds = app.DBManager.NewDataSet(
                    "SELECT FIRST 1 COMPANYNAME FROM SY_PROFILE"
                )
                try:
                    company = ""
                    if ds.RecordCount > 0:
                        company = ds.FindField("COMPANYNAME").AsString
                finally:
                    ds.Close()
                app.Logout()
                msg = f"Connected successfully!\n\nDatabase: {db}"
                if company:
                    msg += f"\nCompany: {company}"
                messagebox.showinfo("Success", msg)
            except Exception as e:
                app.Logout()
                err_msg = str(e).lower()
                if "access violation" in err_msg or "password" in err_msg:
                    messagebox.showerror("Connection Failed",
                                         "Login failed. Please check your username and password.\n\n"
                                         f"Details: {e}")
                else:
                    messagebox.showerror("Connection Failed",
                                         f"Logged in but could not query database.\n\n{e}")
        except Exception as e:
            err_msg = str(e).lower()
            if "access violation" in err_msg:
                messagebox.showerror("Connection Failed",
                                     "Login failed. Please check your username and password.\n\n"
                                     f"Details: {e}")
            else:
                messagebox.showerror("Connection Failed",
                                     f"Could not connect to SQL Account SDK.\n\n{e}")

    # ==================================================================
    # ENTITY MANAGER TAB
    # ==================================================================
    def _build_entity_tab(self):
        tab = self.tabview.tab("Entity Manager")

        # Entity count label
        self.entity_count_label = ctk.CTkLabel(tab, text="", anchor="w", text_color="gray40")
        self.entity_count_label.pack(fill="x", padx=25, pady=(2, 2))

        # Table header
        header_frame = ctk.CTkFrame(tab, fg_color=CLR_BG_SEC, corner_radius=0)
        header_frame.pack(fill="x", padx=20, pady=(0, 0))
        header_frame.columnconfigure(0, weight=0, minsize=30)
        header_frame.columnconfigure(1, weight=0, minsize=30)
        header_frame.columnconfigure(2, weight=0, minsize=80)
        header_frame.columnconfigure(3, weight=1)
        header_frame.columnconfigure(4, weight=0, minsize=60)
        header_frame.columnconfigure(5, weight=0, minsize=130)
        header_frame.columnconfigure(6, weight=0, minsize=50)

        self._ent_check_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(header_frame, text="", variable=self._ent_check_all_var,
                         width=30, fg_color=CLR_PRIMARY,
                         command=self._toggle_check_all_entities
                         ).grid(row=0, column=0, padx=4, pady=4, sticky="w")

        for col, (text, width) in [
            (1, ("#", 30)), (2, ("Prefix", 60)), (3, ("Company Name", 0)),
            (4, ("Strip", 60)), (5, ("Last Synced", 130)), (6, ("", 50)),
        ]:
            lbl = ctk.CTkLabel(header_frame, text=text, font=FONT_SECTION, anchor="center")
            if width > 0:
                lbl.configure(width=width)
            lbl.grid(row=0, column=col, padx=4, pady=4, sticky="ew")

        # Filter row
        ent_filter_row = ctk.CTkFrame(tab, fg_color="white", border_width=1,
                                       border_color="gray80", corner_radius=0)
        ent_filter_row.pack(fill="x", padx=20, pady=(0, 0))
        ent_filter_row.columnconfigure(0, weight=0, minsize=30)
        ent_filter_row.columnconfigure(1, weight=0, minsize=30)
        ent_filter_row.columnconfigure(2, weight=0, minsize=80)
        ent_filter_row.columnconfigure(3, weight=1)
        ent_filter_row.columnconfigure(4, weight=0, minsize=60)
        ent_filter_row.columnconfigure(5, weight=0, minsize=130)
        ent_filter_row.columnconfigure(6, weight=0, minsize=50)

        self._ent_filter_checked_var = ctk.StringVar(value="All")
        self._ent_filter_row_var = ctk.StringVar()
        self._ent_filter_prefix_var = ctk.StringVar()
        self._ent_filter_name_var = ctk.StringVar()
        for var in [self._ent_filter_row_var, self._ent_filter_prefix_var,
                    self._ent_filter_name_var]:
            var.trace_add("write", lambda *_: self._ent_schedule_render())

        # Column 0: Checked filter (dropdown)
        ctk.CTkComboBox(
            ent_filter_row, values=["All", "True", "False"],
            variable=self._ent_filter_checked_var, width=30, height=26,
            font=FONT_CODE_SM, state="readonly",
            command=lambda _: self._ent_schedule_render()
        ).grid(row=0, column=0, padx=4, pady=3, sticky="ew")

        # Column 1: Row # filter
        ctk.CTkEntry(ent_filter_row, textvariable=self._ent_filter_row_var,
                      width=30, height=26, font=FONT_CODE_SM,
                      placeholder_text="#"
                      ).grid(row=0, column=1, padx=4, pady=3, sticky="ew")

        # Column 2: Prefix filter
        ctk.CTkEntry(ent_filter_row, textvariable=self._ent_filter_prefix_var,
                      width=36, height=26, font=FONT_CODE_SM,
                      placeholder_text="Prefix..."
                      ).grid(row=0, column=2, padx=4, pady=3, sticky="ew")

        # Column 3: Name filter
        ctk.CTkEntry(ent_filter_row, textvariable=self._ent_filter_name_var,
                      height=26, font=FONT_CODE_SM,
                      placeholder_text="Name..."
                      ).grid(row=0, column=3, padx=(4, 80), pady=3, sticky="ew")

        # Column 4: Strip filter

        # --- Bottom section (pack with side="bottom" first to reserve space) ---

        # Action buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=10)
        ctk.CTkButton(btn_frame, text="+ Add Entity", fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY,
                       command=self._add_entity_dialog).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Remove Selected", fg_color=CLR_DANGER,
                       hover_color=CLR_DANGER_HOVER,
                       command=self._remove_entity).pack(side="left", padx=10)

        # Grid footer
        ent_footer = ctk.CTkFrame(tab, fg_color=CLR_BG_SEC, corner_radius=0)
        ent_footer.pack(side="bottom", fill="x", padx=20, pady=(0, 0))
        ent_footer.columnconfigure(0, weight=0, minsize=30)
        ent_footer.columnconfigure(1, weight=0, minsize=30)
        ent_footer.columnconfigure(2, weight=0, minsize=80)
        ent_footer.columnconfigure(3, weight=1)
        ent_footer.columnconfigure(4, weight=0, minsize=60)
        ent_footer.columnconfigure(5, weight=0, minsize=130)
        ent_footer.columnconfigure(6, weight=0, minsize=50)

        self._ent_footer_checked_label = ctk.CTkLabel(
            ent_footer, text="", font=FONT_CODE_SM, text_color="gray40")
        self._ent_footer_checked_label.grid(row=0, column=0, padx=4, pady=4, sticky="w")

        self._ent_footer_count_label = ctk.CTkLabel(
            ent_footer, text="", font=FONT_CODE_SM, text_color="gray40")
        self._ent_footer_count_label.grid(row=0, column=1, padx=4, pady=4)

        # Scrollable entity list
        self.entity_scroll = ctk.CTkScrollableFrame(tab, height=300, fg_color="white", corner_radius=0)
        self.entity_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 0))
        self.entity_scroll.columnconfigure(0, weight=0, minsize=30)
        self.entity_scroll.columnconfigure(1, weight=0, minsize=30)
        self.entity_scroll.columnconfigure(2, weight=0, minsize=80)
        self.entity_scroll.columnconfigure(3, weight=1)
        self.entity_scroll.columnconfigure(4, weight=0, minsize=60)
        self.entity_scroll.columnconfigure(5, weight=0, minsize=130)
        self.entity_scroll.columnconfigure(6, weight=0, minsize=50)

        self.entity_widgets = []
        self._refresh_entity_list()

    def _ent_schedule_render(self):
        """Debounce entity search: re-render after 200ms idle."""
        if self._ent_render_timer is not None:
            self.after_cancel(self._ent_render_timer)
        self._ent_render_timer = self.after(200, self._refresh_entity_list)

    def _refresh_entity_list(self):
        # Also refresh category tab entity dropdown if it exists
        if hasattr(self, "_cat_entity_combo"):
            self._refresh_cat_entity_list()

        for widget in self.entity_scroll.winfo_children():
            widget.destroy()
        self.entity_widgets = []

        # Per-column filters
        f_checked = self._ent_filter_checked_var.get() if hasattr(self, "_ent_filter_checked_var") else "All"
        f_row = self._ent_filter_row_var.get().strip() if hasattr(self, "_ent_filter_row_var") else ""
        f_prefix = self._ent_filter_prefix_var.get().lower().strip() if hasattr(self, "_ent_filter_prefix_var") else ""
        f_name = self._ent_filter_name_var.get().lower().strip() if hasattr(self, "_ent_filter_name_var") else ""
        has_filter = bool(f_prefix or f_name or f_row or f_checked != "All")

        if not self.config.entities:
            ctk.CTkLabel(self.entity_scroll, text="No entities configured. Click '+ Add Entity' to begin.",
                          text_color="gray40").grid(row=0, column=0, columnspan=7, pady=20)
            if hasattr(self, "entity_count_label"):
                self.entity_count_label.configure(text="0 entities")
            if hasattr(self, "_ent_footer_checked_label"):
                self._ent_footer_checked_label.configure(text="")
                self._ent_footer_count_label.configure(text="")
            return

        visible_count = 0
        checked_count = 0
        for i, entity in enumerate(self.config.entities):
            # Per-column filters
            if f_checked == "True" and not entity.enabled:
                continue
            if f_checked == "False" and entity.enabled:
                continue
            if f_row and f_row not in str(i + 1):
                continue
            if f_prefix and f_prefix not in (entity.prefix or "").lower():
                continue
            if f_name and f_name not in f"{entity.name} {entity.remark}".lower():
                continue

            if entity.enabled:
                checked_count += 1

            row = visible_count
            visible_count += 1

            # Alternate row colors for readability
            bg = "white" if row % 2 == 0 else "#F3F0FA"

            var = ctk.BooleanVar(value=entity.enabled)
            cb = ctk.CTkCheckBox(self.entity_scroll, text="", variable=var, width=30,
                                  fg_color=CLR_BG_SEC if not entity.enabled else CLR_PRIMARY,
                                  command=lambda idx=i, v=var: self._toggle_entity(idx, v))
            cb.grid(row=row, column=0, padx=4, pady=2, sticky="w")

            ctk.CTkLabel(self.entity_scroll, text=str(i + 1), width=30,
                          font=FONT_CODE_SM, text_color="gray40"
                          ).grid(row=row, column=1, padx=4, pady=2)

            prefix_display = entity.prefix or "-"
            ctk.CTkLabel(self.entity_scroll, text=prefix_display, width=60,
                          font=FONT_CODE_SM,
                          text_color=CLR_PRIMARY).grid(row=row, column=2, padx=4, pady=2)

            name_display = entity.name or "(not connected)"
            if entity.remark:
                name_display += f"  ({entity.remark})"
            ctk.CTkLabel(self.entity_scroll, text=name_display, anchor="w",
                          font=FONT_CODE_SM).grid(
                row=row, column=3, padx=4, pady=2, sticky="ew")

            ctk.CTkLabel(self.entity_scroll, text=entity.customer_code_prefix or "-",
                          width=60, font=FONT_CODE_SM).grid(row=row, column=4, padx=4, pady=2)

            last_sync = entity.last_synced[:19] if entity.last_synced else "Never"
            ctk.CTkLabel(self.entity_scroll, text=last_sync, width=130,
                          font=FONT_CODE_SM, text_color="gray40"
                          ).grid(row=row, column=5, padx=4, pady=2)

            ctk.CTkButton(self.entity_scroll, text="Edit", width=50, height=24,
                           fg_color=CLR_ACCENT, hover_color=CLR_SECONDARY,
                           command=lambda idx=i: self._edit_entity_dialog(idx)).grid(
                row=row, column=6, padx=4, pady=2)

            self.entity_widgets.append({"var": var, "index": i})

        total = len(self.config.entities)
        if hasattr(self, "entity_count_label"):
            if has_filter:
                self.entity_count_label.configure(text=f"{visible_count} of {total} entities shown")
            else:
                self.entity_count_label.configure(text=f"{total} entities")
        if hasattr(self, "_ent_footer_checked_label"):
            self._ent_footer_checked_label.configure(text=f"{checked_count} enabled")
            if has_filter:
                self._ent_footer_count_label.configure(text=f"{visible_count} of {total}")
            else:
                self._ent_footer_count_label.configure(text=f"{total}")

    def _toggle_entity(self, index, var):
        self.config.entities[index].enabled = var.get()
        save_config(self.config)

    def _toggle_check_all_entities(self):
        enabled = self._ent_check_all_var.get()
        self._select_all_entities(enabled)

    def _select_all_entities(self, enabled: bool):
        for entity in self.config.entities:
            entity.enabled = enabled
        save_config(self.config)
        self._refresh_entity_list()

    def _add_entity_dialog(self):
        self._entity_dialog(EntityConfig(), is_new=True)

    def _edit_entity_dialog(self, index):
        self._entity_dialog(self.config.entities[index], is_new=False, index=index)

    def _entity_dialog(self, entity: EntityConfig, is_new=True, index=None):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Source Entity" if is_new else "Edit Source Entity")
        dialog.geometry("650x560")
        dialog.grab_set()

        fields = {}

        # --- Firebird Connection ---
        ctk.CTkLabel(dialog, text="Firebird Connection (Source DB)",
                      font=FONT_SECTION).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(10, 5))

        row = 1
        field_defs = [
            ("FDB Path:", "fb_path", entity.fb_path,
             "e.g. C:\\eStream\\SQLAccounting\\DB\\ACC-0001.FDB"),
            ("Firebird Host:", "fb_host", entity.fb_host, "localhost (or server IP)"),
            ("Firebird User:", "fb_user", entity.fb_user, "SYSDBA"),
            ("Firebird Password:", "fb_password", entity.fb_password, "masterkey"),
        ]

        for label, key, default, hint in field_defs:
            if key == "fb_path":
                lbl_frame = ctk.CTkFrame(dialog, fg_color="transparent")
                lbl_frame.grid(row=row, column=0, sticky="w", padx=15, pady=4)
                ctk.CTkLabel(lbl_frame, text=label, font=FONT_SECTION).pack(side="left")
                self._create_info_icon(lbl_frame,
                                       "e.g. C:\\eStream\\SQLAccounting\\DB\\ACC-0001.FDB")
            else:
                ctk.CTkLabel(dialog, text=label, font=FONT_SECTION).grid(
                    row=row, column=0, sticky="w", padx=15, pady=4)
            var = ctk.StringVar(value=default)
            entry_kwargs = {"textvariable": var, "width": 350, "placeholder_text": hint}
            if key == "fb_password":
                entry_kwargs["show"] = "*"
            entry = ctk.CTkEntry(dialog, **entry_kwargs)
            entry.grid(row=row, column=1, padx=10, pady=4)
            fields[key] = var

            if key == "fb_path":
                ctk.CTkButton(dialog, text="...", width=40, fg_color=CLR_PRIMARY,
                               hover_color=CLR_SECONDARY,
                               command=lambda v=var: self._browse_file(v, [("FDB", "*.FDB")])).grid(
                    row=row, column=2, padx=5, pady=4)
            row += 1

        # --- Transformation Settings ---
        ctk.CTkLabel(dialog, text="Transformation Settings",
                      font=FONT_SECTION).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 5))
        row += 1

        prefix_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        prefix_frame.grid(row=row, column=0, sticky="w", padx=15, pady=4)
        ctk.CTkLabel(prefix_frame, text="Customer Code Prefix to Strip:", font=FONT_SECTION).pack(side="left")
        self._prefix_info_text = "e.g. if customer code is 300-A0001,\nthen prefix is 300-"
        self._create_info_icon(prefix_frame, self._prefix_info_text)
        prefix_var = ctk.StringVar(value=entity.customer_code_prefix)
        ctk.CTkEntry(dialog, textvariable=prefix_var, width=350,
                      placeholder_text="e.g. 300- (will be stripped from customer codes)").grid(
            row=row, column=1, padx=10, pady=4)
        fields["customer_code_prefix"] = prefix_var
        row += 1

        # --- Auto-read info (read-only display) ---
        ctk.CTkLabel(dialog, text="Auto-Read Info (from Company Profile)",
                      font=FONT_SECTION).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 5))
        row += 1

        self._info_name_var = ctk.StringVar(value=entity.name or "(click Test Connection)")
        self._info_remark_var = ctk.StringVar(value=entity.remark or "(click Test Connection)")
        self._info_prefix_var = ctk.StringVar(value=entity.prefix or "(click Test Connection)")

        ctk.CTkLabel(dialog, text="Company Name:", font=FONT_SECTION).grid(
            row=row, column=0, sticky="w", padx=15, pady=2)
        ctk.CTkEntry(dialog, textvariable=self._info_name_var, width=350,
                      state="disabled").grid(row=row, column=1, padx=10, pady=2)
        row += 1

        ctk.CTkLabel(dialog, text="Remark:", font=FONT_SECTION).grid(
            row=row, column=0, sticky="w", padx=15, pady=2)
        ctk.CTkEntry(dialog, textvariable=self._info_remark_var, width=350,
                      state="disabled").grid(row=row, column=1, padx=10, pady=2)
        row += 1

        ep_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        ep_frame.grid(row=row, column=0, sticky="w", padx=15, pady=2)
        ctk.CTkLabel(ep_frame, text="Entity Prefix (ALIAS):", font=FONT_SECTION).pack(side="left")
        self._create_info_icon(ep_frame,
                               "SQL Account: File > Company Profile > More >\nShort Company Name (for consolidate A/C)")
        ctk.CTkEntry(dialog, textvariable=self._info_prefix_var, width=350,
                      state="disabled").grid(row=row, column=1, padx=10, pady=2)
        row += 1

        # --- Buttons (centered footer) ---
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=3, pady=15)

        def _detect_prefix(code: str) -> str:
            """Auto-detect customer code prefix (e.g. '300-' from '300-A0001')."""
            import re
            # Match leading digits/letters followed by a separator (-, /, .)
            m = re.match(r'^([A-Za-z0-9]+[-/.])(.+)$', code)
            if m:
                return m.group(1)
            return ""

        def on_test():
            """Test Firebird connection and auto-read SY_PROFILE + sample customer code."""
            try:
                conn = fdb.connect(
                    host=fields["fb_host"].get(),
                    database=fields["fb_path"].get(),
                    user=fields["fb_user"].get(),
                    password=fields["fb_password"].get(),
                    charset="UTF8",
                )
                cur = conn.cursor()
                cur.execute("SELECT ALIAS, COMPANYNAME, REMARK FROM SY_PROFILE")
                profile_row = cur.fetchone()

                # Read first customer code to auto-detect prefix
                sample_code = ""
                detected_prefix = ""
                try:
                    cur.execute("SELECT FIRST 1 CODE FROM AR_CUSTOMER ORDER BY CODE")
                    cust_row = cur.fetchone()
                    if cust_row:
                        sample_code = (cust_row[0] or "").strip()
                        detected_prefix = _detect_prefix(sample_code)
                except Exception:
                    pass

                cur.close()
                conn.close()

                if profile_row:
                    alias = (profile_row[0] or "").strip()
                    company = (profile_row[1] or "").strip()
                    remark = (profile_row[2] or "").strip()
                    self._info_name_var.set(company)
                    self._info_remark_var.set(remark)
                    self._info_prefix_var.set(alias)
                    entity.name = company
                    entity.remark = remark
                    entity.prefix = alias
                    # Auto-fill prefix if detected and field is default/empty
                    if detected_prefix and fields["customer_code_prefix"].get() in ("", "300-"):
                        fields["customer_code_prefix"].set(detected_prefix)

                    msg = f"Connected!\n\nCompany: {company}\nAlias/Prefix: {alias}"
                    if remark:
                        msg += f"\nRemark: {remark}"
                    if sample_code:
                        msg += f"\n\nSample Customer Code: {sample_code}"
                        if detected_prefix:
                            msg += f"\nDetected Prefix: {detected_prefix}"
                    messagebox.showinfo("Success", msg)
                else:
                    messagebox.showwarning("Warning", "Connected but SY_PROFILE is empty.")
            except Exception as e:
                messagebox.showerror("Connection Failed", str(e))

        def on_save():
            for key, var in fields.items():
                setattr(entity, key, var.get())

            if is_new:
                self.config.add_entity(entity)
            else:
                self.config.entities[index] = entity

            save_config(self.config)
            self._refresh_entity_list()
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Test Connection", fg_color=CLR_ACCENT,
                       hover_color=CLR_SECONDARY, command=on_test).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Save", fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY, command=on_save).pack(side="left", padx=10)

    def _remove_entity(self):
        selected = [w for w in self.entity_widgets if w["var"].get()]
        if not selected:
            messagebox.showwarning("No Selection", "Please check the entities you want to remove.")
            return

        if not messagebox.askyesno("Confirm", f"Remove {len(selected)} entity(ies)?"):
            return

        # Remove in reverse order to maintain indices
        for w in sorted(selected, key=lambda x: x["index"], reverse=True):
            self.config.remove_entity(w["index"])

        save_config(self.config)
        self._refresh_entity_list()

    # ==================================================================
    # CATEGORY MAPPING TAB
    # ==================================================================
    def _build_category_tab(self):
        tab = self.tabview.tab("Category Mapping")

        # Control area: grid layout for aligned labels + fields
        ctrl_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=20, pady=(10, 5))

        # Row 0: Entity
        ctk.CTkLabel(ctrl_frame, text="Entity:", font=FONT_SECTION
                      ).grid(row=0, column=0, sticky="w", padx=(0, 5), pady=3)
        self._cat_entity_values = []
        self._cat_entity_combo = ctk.CTkComboBox(
            ctrl_frame, values=["(no entities)"], width=350, state="readonly")
        self._cat_entity_combo.grid(row=0, column=1, sticky="w", padx=5, pady=3)
        self._refresh_cat_entity_list()
        ctk.CTkButton(ctrl_frame, text="Load Customers", fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY,
                       command=self._cat_load_customers
                       ).grid(row=0, column=2, sticky="ew", padx=5, pady=3)

        # Row 1: Set Checked
        ctk.CTkLabel(ctrl_frame, text="Set Checked:", font=FONT_SECTION
                      ).grid(row=1, column=0, sticky="w", padx=(0, 5), pady=3)
        self._cat_bulk_combo = ctk.CTkComboBox(
            ctrl_frame, values=["(load categories first)"], width=350,
            state="disabled")
        self._cat_bulk_combo.grid(row=1, column=1, sticky="w", padx=5, pady=3)
        ctk.CTkButton(ctrl_frame, text="Load Categories",
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=self._cat_refresh_categories
                       ).grid(row=1, column=2, sticky="ew", padx=5, pady=3)

        # Status label
        self._cat_status_label = ctk.CTkLabel(tab,
                                               text="Select an entity and click Load Customers.",
                                               anchor="w", text_color="gray40")
        self._cat_status_label.pack(fill="x", padx=25, pady=(2, 2))

        # Table header with check-all checkbox
        cat_header = ctk.CTkFrame(tab, fg_color=CLR_BG_SEC, corner_radius=0)
        cat_header.pack(fill="x", padx=20, pady=(0, 0))
        cat_header.columnconfigure(0, weight=0, minsize=30)
        cat_header.columnconfigure(1, weight=0, minsize=30)
        cat_header.columnconfigure(2, weight=0, minsize=120)
        cat_header.columnconfigure(3, weight=1)
        cat_header.columnconfigure(4, weight=0, minsize=80)
        cat_header.columnconfigure(5, weight=0, minsize=250)

        self._cat_check_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(cat_header, text="", variable=self._cat_check_all_var,
                         width=30, fg_color=CLR_PRIMARY,
                         command=self._cat_toggle_check_all
                         ).grid(row=0, column=0, padx=4, pady=4, sticky="w")

        for col, (text, width) in [
            (1, ("#", 30)), (2, ("Customer Code", 120)),
            (3, ("Company Name", 0)), (4, ("Currency", 80)), (5, ("Category", 250)),
        ]:
            lbl = ctk.CTkLabel(cat_header, text=text, font=FONT_SECTION, anchor="center")
            if width > 0:
                lbl.configure(width=width)
            lbl.grid(row=0, column=col, padx=4, pady=4, sticky="ew")

        # Filter row (per-column filter inputs)
        cat_filter_row = ctk.CTkFrame(tab, fg_color="white", border_width=1,
                                       border_color="gray80", corner_radius=0)
        cat_filter_row.pack(fill="x", padx=20, pady=(0, 0))
        cat_filter_row.columnconfigure(0, weight=0, minsize=30)
        cat_filter_row.columnconfigure(1, weight=0, minsize=30)
        cat_filter_row.columnconfigure(2, weight=0, minsize=120)
        cat_filter_row.columnconfigure(3, weight=1)
        cat_filter_row.columnconfigure(4, weight=0, minsize=80)
        cat_filter_row.columnconfigure(5, weight=0, minsize=250)

        self._cat_filter_checked_var = ctk.StringVar(value="All")
        self._cat_filter_row_var = ctk.StringVar()
        self._cat_filter_code_var = ctk.StringVar()
        self._cat_filter_name_var = ctk.StringVar()
        self._cat_filter_currency_var = ctk.StringVar()
        self._cat_filter_category_var = ctk.StringVar(value="All")

        for var in [self._cat_filter_row_var, self._cat_filter_code_var,
                    self._cat_filter_name_var, self._cat_filter_currency_var]:
            var.trace_add("write", lambda *_: self._cat_schedule_render())

        # Column 0: Checked filter (dropdown)
        checked_combo = ctk.CTkComboBox(
            cat_filter_row, values=["All", "True", "False"],
            variable=self._cat_filter_checked_var, width=30, height=26,
            font=FONT_CODE_SM, state="readonly",
            command=lambda _: self._cat_schedule_render())
        checked_combo.grid(row=0, column=0, padx=4, pady=3, sticky="ew")

        # Column 1: Row # filter
        ctk.CTkEntry(cat_filter_row, textvariable=self._cat_filter_row_var,
                      width=30, height=26, font=FONT_CODE_SM,
                      placeholder_text="#"
                      ).grid(row=0, column=1, padx=4, pady=3, sticky="ew")

        # Column 2: Code filter
        ctk.CTkEntry(cat_filter_row, textvariable=self._cat_filter_code_var,
                      width=120, height=26, font=FONT_CODE_SM,
                      placeholder_text="Code..."
                      ).grid(row=0, column=2, padx=4, pady=3, sticky="ew")

        # Column 3: Name filter
        ctk.CTkEntry(cat_filter_row, textvariable=self._cat_filter_name_var,
                      height=26, font=FONT_CODE_SM,
                      placeholder_text="Name..."
                      ).grid(row=0, column=3, padx=4, pady=3, sticky="ew")

        # Column 4: Currency filter
        ctk.CTkEntry(cat_filter_row, textvariable=self._cat_filter_currency_var,
                      width=80, height=26, font=FONT_CODE_SM,
                      placeholder_text="Currency..."
                      ).grid(row=0, column=4, padx=4, pady=3, sticky="ew")

        # Column 5: Category filter (dropdown)
        self._cat_filter_category_combo = ctk.CTkComboBox(
            cat_filter_row, values=["All", "(none)"],
            variable=self._cat_filter_category_var, width=250, height=26,
            font=FONT_CODE_SM, state="readonly",
            command=lambda _: self._cat_schedule_render())
        self._cat_filter_category_combo.grid(row=0, column=5, padx=4, pady=3, sticky="ew")

        # --- Bottom section (pack with side="bottom" first to reserve space) ---

        # Action buttons (centered footer)
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=10)
        ctk.CTkButton(btn_frame, text="Apply", width=70, fg_color=CLR_ACCENT,
                       hover_color=CLR_SECONDARY,
                       command=self._cat_bulk_apply).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Save Mapping", fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY,
                       command=self._cat_save_mapping).pack(side="left", padx=10)

        # Pagination bar
        page_frame = ctk.CTkFrame(tab, fg_color="transparent")
        page_frame.pack(side="bottom", fill="x", padx=20, pady=(4, 0))

        self._cat_prev_btn = ctk.CTkButton(
            page_frame, text="< Prev", width=60, height=26,
            fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
            command=self._cat_prev_page, state="disabled")
        self._cat_prev_btn.pack(side="left", padx=2)

        self._cat_page_label = ctk.CTkLabel(
            page_frame, text="", font=FONT_CAPTION, text_color="gray40")
        self._cat_page_label.pack(side="left", padx=10)

        self._cat_next_btn = ctk.CTkButton(
            page_frame, text="Next >", width=60, height=26,
            fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
            command=self._cat_next_page, state="disabled")
        self._cat_next_btn.pack(side="left", padx=2)

        ctk.CTkLabel(page_frame, text="  Show:", font=FONT_CAPTION
                      ).pack(side="left", padx=(15, 3))
        self._cat_page_size_var = ctk.StringVar(value="50")
        page_size_combo = ctk.CTkComboBox(
            page_frame, values=["50", "100", "200", "All"],
            variable=self._cat_page_size_var, width=70, height=26,
            state="readonly", command=self._cat_page_size_changed)
        page_size_combo.pack(side="left", padx=2)

        # Grid footer (summary counts)
        cat_footer = ctk.CTkFrame(tab, fg_color=CLR_BG_SEC, corner_radius=0)
        cat_footer.pack(side="bottom", fill="x", padx=20, pady=(0, 0))
        cat_footer.columnconfigure(0, weight=0, minsize=30)
        cat_footer.columnconfigure(1, weight=0, minsize=30)
        cat_footer.columnconfigure(2, weight=0, minsize=120)
        cat_footer.columnconfigure(3, weight=1)
        cat_footer.columnconfigure(4, weight=0, minsize=80)
        cat_footer.columnconfigure(5, weight=0, minsize=250)

        self._cat_footer_checked_label = ctk.CTkLabel(
            cat_footer, text="", font=FONT_CODE_SM, text_color="gray40")
        self._cat_footer_checked_label.grid(row=0, column=0, padx=4, pady=4, sticky="w")

        self._cat_footer_code_label = ctk.CTkLabel(
            cat_footer, text="", font=FONT_CODE_SM, text_color="gray40")
        self._cat_footer_code_label.grid(row=0, column=2, padx=4, pady=4)

        # --- Scrollable grid (fills remaining space) ---
        self._cat_scroll = ctk.CTkScrollableFrame(tab, height=300, fg_color="white", corner_radius=0)
        self._cat_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 0))
        self._cat_scroll.columnconfigure(0, weight=0, minsize=30)
        self._cat_scroll.columnconfigure(1, weight=0, minsize=30)
        self._cat_scroll.columnconfigure(2, weight=0, minsize=120)
        self._cat_scroll.columnconfigure(3, weight=1)
        self._cat_scroll.columnconfigure(4, weight=0, minsize=80)
        self._cat_scroll.columnconfigure(5, weight=0, minsize=250)

        # State
        self._cat_customers = []       # List of (code, company_name) from source DB
        self._cat_combos = []          # List of SearchableComboBox widgets (visible rows)
        self._cat_check_vars = []      # List of BooleanVar (visible rows)
        self._cat_checked_codes = set() # Persistent set of checked customer codes
        self._cat_visible_indices = [] # Indices into _cat_customers for visible rows
        self._cat_pending_map = {}     # Unsaved category selections {code: display_val}
        self._cat_entity_idx = -1      # Currently selected entity index
        self._cat_cat_values = []      # Cached category display values
        self._cat_render_timer = None  # Debounce timer for search
        self._cat_page = 0            # Current page index (0-based)
        self._cat_page_size = 50      # Rows per page
        self._cat_row_pool = []       # Recycled row widgets: [(chk, var, row_lbl, code_lbl, name_lbl, cur_lbl, combo)]
        self._cat_no_data_label = None  # "No customers" label (shown/hidden)

    def _cat_prev_page(self):
        """Go to previous page."""
        if self._cat_page > 0:
            if self._cat_combos:
                self._cat_snapshot_combos()
            self._cat_page -= 1
            self._cat_render_rows()

    def _cat_next_page(self):
        """Go to next page."""
        if self._cat_combos:
            self._cat_snapshot_combos()
        self._cat_page += 1
        self._cat_render_rows()

    def _cat_page_size_changed(self, value=None):
        """Handle page size dropdown change."""
        if self._cat_combos:
            self._cat_snapshot_combos()
        val = self._cat_page_size_var.get()
        if val == "All":
            self._cat_page_size = 999999
        else:
            self._cat_page_size = int(val)
        self._cat_page = 0
        self._cat_render_rows()

    def _refresh_cat_entity_list(self):
        """Refresh the entity dropdown in the Category Mapping tab."""
        self._cat_entity_values = []
        values = []
        for i, entity in enumerate(self.config.entities):
            display = f"{entity.prefix or '?'} - {entity.name or '(not connected)'}"
            values.append(display)
            self._cat_entity_values.append(i)

        if values:
            self._cat_entity_combo.configure(values=values, state="readonly")
            self._cat_entity_combo.set(values[0])
        else:
            self._cat_entity_combo.configure(values=["(no entities)"], state="disabled")
            self._cat_entity_combo.set("(no entities)")

    def _cat_get_selected_entity_idx(self) -> int:
        """Get the index of the currently selected entity in the combo."""
        current = self._cat_entity_combo.get()
        values = self._cat_entity_combo.cget("values")
        if current in values:
            idx_in_list = list(values).index(current)
            if idx_in_list < len(self._cat_entity_values):
                return self._cat_entity_values[idx_in_list]
        return -1

    def _cat_schedule_render(self):
        """Debounce search: re-render rows after 200ms idle."""
        self._cat_page = 0  # Reset to first page on search
        if self._cat_render_timer is not None:
            self.after_cancel(self._cat_render_timer)
        self._cat_render_timer = self.after(200, self._cat_render_rows)

    def _cat_toggle_check_all(self):
        """Check/uncheck all VISIBLE (filtered) rows."""
        val = self._cat_check_all_var.get()
        for i, var in enumerate(self._cat_check_vars):
            var.set(val)
            if i < len(self._cat_visible_indices):
                code = self._cat_customers[self._cat_visible_indices[i]][0]
                if val:
                    self._cat_checked_codes.add(code)
                else:
                    self._cat_checked_codes.discard(code)
        self._cat_update_footer_checked()

    def _cat_on_check_toggle(self, code: str, var):
        """Handle individual checkbox toggle — update checked set and footer."""
        if var.get():
            self._cat_checked_codes.add(code)
        else:
            self._cat_checked_codes.discard(code)
        self._cat_update_footer_checked()

    def _cat_update_footer_checked(self):
        """Update the checked count in the grid footer."""
        self._cat_footer_checked_label.configure(
            text=f"{len(self._cat_checked_codes)} checked")

    def _cat_load_customers(self):
        """Load customers from the selected entity's source DB."""
        idx = self._cat_get_selected_entity_idx()
        if idx < 0 or idx >= len(self.config.entities):
            messagebox.showwarning("No Entity", "Please select an entity first.")
            return

        entity = self.config.entities[idx]
        self._cat_entity_idx = idx

        if not entity.fb_path:
            messagebox.showwarning("Not Configured",
                                   "This entity has no FDB path configured.\n"
                                   "Please configure it in Entity Manager first.")
            return

        # Load categories if not cached
        if not self._company_categories:
            self._fetch_company_categories()

        # Build category values for dropdowns
        self._cat_cat_values = ["(none)"]
        for cat in self._company_categories:
            self._cat_cat_values.append(f"{cat['code']} - {cat['description']}")

        # Update bulk combo
        if len(self._cat_cat_values) > 1:
            self._cat_bulk_combo.configure(values=self._cat_cat_values, state="readonly")
            self._cat_bulk_combo.set("(none)")
        else:
            self._cat_bulk_combo.configure(values=["(no categories loaded)"], state="disabled")

        # Update category filter dropdown
        filter_cat_values = ["All"] + self._cat_cat_values
        self._cat_filter_category_combo.configure(values=filter_cat_values)
        self._cat_filter_category_var.set("All")

        # Read customers from source DB
        conn = None
        try:
            conn = fdb.connect(
                host=entity.fb_host,
                database=entity.fb_path,
                user=entity.fb_user,
                password=entity.fb_password,
                charset="UTF8",
            )
            cur = conn.cursor()
            cur.execute("SELECT CODE, COMPANYNAME, CURRENCYCODE FROM AR_CUSTOMER ORDER BY CODE")
            self._cat_customers = []
            for row in cur.fetchall():
                code = (row[0] or "").strip()
                name = (row[1] or "").strip()
                currency = (row[2] or "").strip()
                if code:
                    self._cat_customers.append((code, name, currency))
            cur.close()
        except Exception as e:
            messagebox.showerror("Connection Failed",
                                 f"Could not read customers from source DB.\n\n{e}")
            return
        finally:
            if conn:
                conn.close()

        # Initialize pending map from saved config and clear checked state
        self._cat_pending_map = {}
        self._cat_checked_codes = set()
        for code, cat_code in entity.customer_category_map.items():
            # Convert saved code to display value
            for cv in self._cat_cat_values:
                if cv.startswith(f"{cat_code} - ") or cv == cat_code:
                    self._cat_pending_map[code] = cv
                    break

        # Cancel any pending debounce, reset filter/page, clear search, render fresh
        if self._cat_render_timer is not None:
            self.after_cancel(self._cat_render_timer)
            self._cat_render_timer = None
        self._cat_combos = []  # Prevent snapshot of old entity's combos
        self._cat_check_vars = []
        self._cat_visible_indices = []
        # Pool survives entity switch — _cat_render_rows will reuse/hide as needed
        self._cat_page = 0
        self._cat_filter_checked_var.set("All")
        self._cat_filter_row_var.set("")
        self._cat_filter_code_var.set("")
        self._cat_filter_name_var.set("")
        self._cat_filter_currency_var.set("")
        self._cat_filter_category_var.set("All")
        # Cancel again in case set("") triggered a new timer
        if self._cat_render_timer is not None:
            self.after_cancel(self._cat_render_timer)
            self._cat_render_timer = None
        self._cat_render_rows()

    def _cat_snapshot_combos(self):
        """Capture current combo selections and checked state before re-render."""
        for i, combo in enumerate(self._cat_combos):
            if i < len(self._cat_visible_indices):
                orig_idx = self._cat_visible_indices[i]
                code = self._cat_customers[orig_idx][0]
                # Snapshot category selection
                val = combo.get()
                if val and val != "(none)":
                    self._cat_pending_map[code] = val
                else:
                    self._cat_pending_map[code] = "(none)"
                # Snapshot checked state
                if i < len(self._cat_check_vars):
                    if self._cat_check_vars[i].get():
                        self._cat_checked_codes.add(code)
                    else:
                        self._cat_checked_codes.discard(code)

    def _cat_render_rows(self):
        """Render the customer grid with widget recycling for performance."""
        import math

        # Snapshot current selections before updating widgets
        if self._cat_combos:
            self._cat_snapshot_combos()

        self._cat_combos = []
        self._cat_check_vars = []
        self._cat_visible_indices = []

        if not self._cat_customers:
            # Hide all pooled rows
            for widgets in self._cat_row_pool:
                chk, var, row_lbl, code_lbl, name_lbl, cur_lbl, combo = widgets
                chk.grid_remove()
                row_lbl.grid_remove()
                code_lbl.grid_remove()
                name_lbl.grid_remove()
                cur_lbl.grid_remove()
                combo.grid_remove()
            # Show "no data" label
            if not self._cat_no_data_label:
                self._cat_no_data_label = ctk.CTkLabel(
                    self._cat_scroll, text="No customers found in source DB.",
                    text_color="gray40")
            self._cat_no_data_label.grid(row=0, column=0, columnspan=6, pady=20)
            self._cat_status_label.configure(text="0 customers")
            self._cat_page_label.configure(text="")
            self._cat_prev_btn.configure(state="disabled")
            self._cat_next_btn.configure(state="disabled")
            self._cat_footer_checked_label.configure(text="")
            self._cat_footer_code_label.configure(text="")
            return

        # Hide "no data" label if visible
        if self._cat_no_data_label:
            self._cat_no_data_label.grid_remove()

        cat_values = self._cat_cat_values
        entity = self.config.entities[self._cat_entity_idx]

        # Per-column filters
        f_checked = self._cat_filter_checked_var.get()
        f_row = self._cat_filter_row_var.get().strip()
        f_code = self._cat_filter_code_var.get().lower().strip()
        f_name = self._cat_filter_name_var.get().lower().strip()
        f_currency = self._cat_filter_currency_var.get().lower().strip()
        f_category = self._cat_filter_category_var.get().strip()

        # Step 1: Build filtered list
        filtered = []
        mapped_total = 0

        for i, (code, name, currency) in enumerate(self._cat_customers):
            has_mapping = code in self._cat_pending_map or code in entity.customer_category_map
            if has_mapping:
                mapped_total += 1

            # Apply per-column filters
            if f_checked == "True" and code not in self._cat_checked_codes:
                continue
            if f_checked == "False" and code in self._cat_checked_codes:
                continue
            if f_row and f_row not in str(i + 1):
                continue
            if f_code and f_code not in code.lower():
                continue
            if f_name and f_name not in name.lower():
                continue
            if f_currency and f_currency not in currency.lower():
                continue
            if f_category and f_category != "All":
                cat_display = self._cat_pending_map.get(code, "")
                if not cat_display:
                    saved_code = entity.customer_category_map.get(code, "")
                    if saved_code:
                        for cv in cat_values:
                            if cv.startswith(f"{saved_code} - ") or cv == saved_code:
                                cat_display = cv
                                break
                if f_category == "(none)":
                    # Show only unmapped customers
                    if cat_display and cat_display != "(none)":
                        continue
                else:
                    # Match exact category selection
                    if cat_display != f_category:
                        continue

            filtered.append(i)

        # Step 2: Pagination
        total_filtered = len(filtered)
        page_size = self._cat_page_size
        total_pages = max(1, math.ceil(total_filtered / page_size)) if page_size < 999999 else 1

        # Clamp page
        if self._cat_page >= total_pages:
            self._cat_page = max(0, total_pages - 1)

        start = self._cat_page * page_size
        end = min(start + page_size, total_filtered)
        page_items = filtered[start:end]

        # Step 3: Update rows using widget recycling
        needed = len(page_items)
        scroll_inner = self._cat_scroll._parent_frame

        # Freeze layout — suppress per-widget geometry recalculations
        scroll_inner.pack_propagate(False)

        # Create new pool rows if needed (plain tk widgets for speed)
        while len(self._cat_row_pool) < needed:
            var = tk.BooleanVar()
            chk = tk.Checkbutton(self._cat_scroll, variable=var,
                                  bg="white", activebackground="white",
                                  highlightthickness=0, bd=0)
            row_lbl = tk.Label(self._cat_scroll, text="", width=5, anchor="center",
                               font=FONT_CODE_SM, fg="gray40", bg="white")
            code_lbl = tk.Label(self._cat_scroll, text="", width=14, anchor="w",
                                font=FONT_CODE_SM, bg="white")
            name_lbl = tk.Label(self._cat_scroll, text="", anchor="w",
                                font=FONT_CODE_SM, bg="white")
            cur_lbl = tk.Label(self._cat_scroll, text="", width=10, anchor="center",
                               font=FONT_CODE_SM, fg="gray40", bg="white")
            combo = SearchableComboBox(self._cat_scroll, values=cat_values, width=250)
            self._cat_row_pool.append((chk, var, row_lbl, code_lbl, name_lbl, cur_lbl, combo))

        # Update visible rows with new data
        for row, orig_idx in enumerate(page_items):
            code, name, currency = self._cat_customers[orig_idx]
            self._cat_visible_indices.append(orig_idx)

            chk, var, row_lbl, code_lbl, name_lbl, cur_lbl, combo = self._cat_row_pool[row]

            # Update checkbox
            var.set(code in self._cat_checked_codes)
            chk.configure(command=lambda c=code, v=var: self._cat_on_check_toggle(c, v))
            chk.configure(variable=var)
            chk.grid(row=row, column=0, padx=4, pady=2, sticky="w")
            self._cat_check_vars.append(var)

            # Update labels
            row_lbl.configure(text=str(orig_idx + 1))
            row_lbl.grid(row=row, column=1, padx=4, pady=2)

            code_lbl.configure(text=code)
            code_lbl.grid(row=row, column=2, padx=4, pady=2)

            name_lbl.configure(text=name)
            name_lbl.grid(row=row, column=3, padx=4, pady=2, sticky="ew")

            cur_lbl.configure(text=currency)
            cur_lbl.grid(row=row, column=4, padx=4, pady=2)

            # Update combo values and selection
            combo.configure(values=cat_values)
            display_val = self._cat_pending_map.get(code, "")
            if not display_val:
                saved_code = entity.customer_category_map.get(code, "")
                if saved_code:
                    for cv in cat_values:
                        if cv.startswith(f"{saved_code} - ") or cv == saved_code:
                            display_val = cv
                            break
            if display_val and display_val in cat_values:
                combo.set(display_val)
            else:
                combo.set("(none)")
            combo.grid(row=row, column=5, padx=4, pady=2)
            self._cat_combos.append(combo)

        # Hide excess pool rows
        for row in range(needed, len(self._cat_row_pool)):
            chk, var, row_lbl, code_lbl, name_lbl, cur_lbl, combo = self._cat_row_pool[row]
            chk.grid_remove()
            row_lbl.grid_remove()
            code_lbl.grid_remove()
            name_lbl.grid_remove()
            cur_lbl.grid_remove()
            combo.grid_remove()

        # Thaw layout — single geometry pass
        scroll_inner.pack_propagate(True)

        # Reset check-all
        self._cat_check_all_var.set(False)

        # Update page navigation
        if total_filtered == 0:
            self._cat_page_label.configure(text="No results")
        elif page_size >= 999999:
            self._cat_page_label.configure(text=f"Showing all {total_filtered}")
        else:
            self._cat_page_label.configure(
                text=f"Page {self._cat_page + 1} of {total_pages}  "
                     f"({start + 1}-{end} of {total_filtered})")
        self._cat_prev_btn.configure(
            state="normal" if self._cat_page > 0 else "disabled")
        self._cat_next_btn.configure(
            state="normal" if self._cat_page < total_pages - 1 else "disabled")

        # Update status
        total = len(self._cat_customers)
        unmapped_total = total - mapped_total
        self._cat_status_label.configure(
            text=f"{total} customers, {mapped_total} mapped, {unmapped_total} unmapped")

        # Update grid footer counts
        checked_count = len(self._cat_checked_codes)
        self._cat_footer_checked_label.configure(text=f"{checked_count} checked")
        total = len(self._cat_customers)
        if total_filtered == total:
            # No search filter active
            if page_size >= 999999 or total_filtered == len(page_items):
                self._cat_footer_code_label.configure(text=f"{total} codes")
            else:
                self._cat_footer_code_label.configure(
                    text=f"{len(page_items)} of {total} codes")
        else:
            # Search filter active — show filtered of total
            self._cat_footer_code_label.configure(
                text=f"{total_filtered} of {total} codes")

    def _cat_bulk_apply(self):
        """Apply the bulk category selection to checked customer rows."""
        bulk_val = self._cat_bulk_combo.get()
        if not bulk_val or bulk_val in ("(no categories loaded)",
                                         "(load categories first)"):
            messagebox.showwarning("No Category", "Please select a category to apply.")
            return

        applied = 0
        for i, var in enumerate(self._cat_check_vars):
            if var.get():
                self._cat_combos[i].set(bulk_val)
                orig_idx = self._cat_visible_indices[i]
                code = self._cat_customers[orig_idx][0]
                if bulk_val == "(none)":
                    # Explicitly mark as cleared
                    self._cat_pending_map[code] = "(none)"
                else:
                    self._cat_pending_map[code] = bulk_val
                applied += 1

        if applied == 0:
            messagebox.showwarning("No Selection",
                                   "Please check the customers you want to apply the category to.")
        else:
            messagebox.showinfo("Applied",
                                f"Set {applied} checked customer(s) to: {bulk_val}")

    def _cat_refresh_categories(self):
        """Refresh company categories from consol DB."""
        self._company_categories = []
        self._fetch_company_categories()

        if self._company_categories:
            self._cat_cat_values = ["(none)"]
            for cat in self._company_categories:
                self._cat_cat_values.append(f"{cat['code']} - {cat['description']}")

            self._cat_bulk_combo.configure(values=self._cat_cat_values, state="readonly")

            # Update category filter dropdown
            filter_cat_values = ["All"] + self._cat_cat_values
            self._cat_filter_category_combo.configure(values=filter_cat_values)

            # Update all existing row combos
            for combo in self._cat_combos:
                current = combo.get()
                combo.configure(values=self._cat_cat_values)
                if current in self._cat_cat_values:
                    combo.set(current)
                else:
                    combo.set("(none)")

            messagebox.showinfo("Refreshed",
                                f"Loaded {len(self._company_categories)} company categories.")
        else:
            messagebox.showwarning("No Categories",
                                   "Could not load categories.\n"
                                   "Please configure Consol DB in Settings first.")

    def _cat_save_mapping(self):
        """Save the current customer-to-category mapping to config."""
        if self._cat_entity_idx < 0 or self._cat_entity_idx >= len(self.config.entities):
            messagebox.showwarning("No Entity", "Please load customers first.")
            return

        # Snapshot current visible combos into pending map
        self._cat_snapshot_combos()

        entity = self.config.entities[self._cat_entity_idx]
        new_map = {}
        unmapped = 0

        for code, name, *_ in self._cat_customers:
            display_val = self._cat_pending_map.get(code, "")
            if display_val and display_val != "(none)":
                cat_code = display_val.split(" - ", 1)[0].strip()
                new_map[code] = cat_code
            elif code in self._cat_pending_map:
                # Explicitly set to (none) — do not save mapping
                unmapped += 1
            else:
                # Never touched (not on any rendered page) — keep existing
                existing = entity.customer_category_map.get(code, "")
                if existing:
                    new_map[code] = existing
                else:
                    unmapped += 1

        entity.customer_category_map = new_map
        save_config(self.config)

        total = len(self._cat_customers)
        mapped = total - unmapped
        self._cat_status_label.configure(
            text=f"{total} customers, {mapped} mapped, {unmapped} unmapped")

        messagebox.showinfo("Saved",
                            f"Category mapping saved for '{entity.name}'.\n\n"
                            f"{mapped} mapped, {unmapped} unmapped.")

    # ==================================================================
    # SYNC DASHBOARD TAB
    # ==================================================================
    def _build_sync_tab(self):
        tab = self.tabview.tab("Sync")

        # --- Unified controls grid ---
        ctrl_frame = ctk.CTkFrame(tab)
        ctrl_frame.pack(fill="x", padx=20, pady=(10, 5))
        ctrl_frame.columnconfigure(0, weight=0, minsize=150)
        ctrl_frame.columnconfigure(1, weight=1)

        # Row 0: Master Data
        ctk.CTkLabel(ctrl_frame, text="Master Data:",
                      font=FONT_SECTION,
                      anchor="w").grid(row=0, column=0, padx=(10, 5), pady=(8, 4), sticky="w")

        self.module_vars = {}
        self._master_labels = {
            "Customer": "Customer",
        }
        self.master_vars = {}
        for key in self._master_labels:
            self.master_vars[key] = ctk.BooleanVar(value=True)
        self.sync_cust_var = self.master_vars["Customer"]  # backward compat

        master_ctrl = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        master_ctrl.grid(row=0, column=1, padx=5, pady=(8, 4), sticky="w")
        self._master_summary_label = ctk.CTkLabel(master_ctrl, text="",
                                                    font=FONT_BODY, text_color=CLR_TEXT_MUTED)
        self._master_summary_label.pack(side="left", padx=(0, 8))
        self._update_master_summary()
        ctk.CTkButton(master_ctrl, text="...", width=30, height=26,
                       fg_color=CLR_PRIMARY, hover_color=CLR_SECONDARY,
                       command=self._open_master_data_popup).pack(side="left")

        # Row 1: Transaction Data
        ctk.CTkLabel(ctrl_frame, text="Transaction Data:",
                      font=FONT_SECTION,
                      anchor="w").grid(row=1, column=0, padx=(10, 5), pady=4, sticky="w")

        self._txn_labels = {
            "IV": "Customer Invoice",
            "DN": "Customer Debit Note",
            "CN": "Customer Credit Note",
            "CT": "Customer Contra",
            "PM": "Customer Payment",
            "CF": "Customer Refund",
        }
        for mod in IMPORT_ORDER:
            self.module_vars[mod] = ctk.BooleanVar(value=True)

        txn_ctrl = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        txn_ctrl.grid(row=1, column=1, padx=5, pady=4, sticky="w")
        self._txn_summary_label = ctk.CTkLabel(txn_ctrl, text="",
                                                 font=FONT_BODY, text_color=CLR_TEXT_MUTED)
        self._txn_summary_label.pack(side="left", padx=(0, 8))
        self._update_txn_summary()
        ctk.CTkButton(txn_ctrl, text="...", width=30, height=26,
                       fg_color=CLR_PRIMARY, hover_color=CLR_SECONDARY,
                       command=self._open_txn_data_popup).pack(side="left")

        # Row 2: Date Range
        self.date_filter_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(ctrl_frame, text="Date Range:",
                         font=FONT_SECTION,
                         variable=self.date_filter_var,
                         command=self._toggle_date_filter
                         ).grid(row=2, column=0, padx=(10, 5), pady=4, sticky="w")

        date_ctrl = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        date_ctrl.grid(row=2, column=1, padx=5, pady=4, sticky="w")

        self._date_from_label = ctk.CTkLabel(date_ctrl, text="From:",
                                              font=FONT_SECTION)
        self._date_from_label.pack(side="left", padx=(0, 5))

        self.date_from_var = ctk.StringVar()
        self._date_from_display = ctk.CTkEntry(date_ctrl, textvariable=self.date_from_var,
                                                width=110, placeholder_text="DD/MM/YYYY",
                                                state="disabled")
        self._date_from_display.pack(side="left", padx=2)

        self._date_from_pick_btn = ctk.CTkButton(
            date_ctrl, text="...", width=30, height=28, state="disabled",
            fg_color=CLR_PRIMARY, hover_color=CLR_SECONDARY,
            command=lambda: self._open_date_picker(self.date_from_var))
        self._date_from_pick_btn.pack(side="left", padx=(1, 10))

        self._date_to_label = ctk.CTkLabel(date_ctrl, text="To:",
                                            font=FONT_SECTION)
        self._date_to_label.pack(side="left", padx=(0, 5))

        self.date_to_var = ctk.StringVar()
        self._date_to_display = ctk.CTkEntry(date_ctrl, textvariable=self.date_to_var,
                                              width=110, placeholder_text="DD/MM/YYYY",
                                              state="disabled")
        self._date_to_display.pack(side="left", padx=2)

        self._date_to_pick_btn = ctk.CTkButton(
            date_ctrl, text="...", width=30, height=28, state="disabled",
            fg_color=CLR_PRIMARY, hover_color=CLR_SECONDARY,
            command=lambda: self._open_date_picker(self.date_to_var))
        self._date_to_pick_btn.pack(side="left", padx=1)

        # Set default date values and enable fields
        self._init_default_dates()
        self._toggle_date_filter()

        # Row 3: Sync Mode
        ctk.CTkLabel(ctrl_frame, text="Sync Mode:",
                      font=FONT_SECTION, anchor="w"
                      ).grid(row=3, column=0, padx=(10, 5), pady=(4, 8), sticky="w")

        mode_ctrl = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        mode_ctrl.grid(row=3, column=1, padx=5, pady=(4, 8), sticky="w")
        self.sync_mode_var = ctk.StringVar(value="skip")
        ctk.CTkRadioButton(mode_ctrl, text="Skip existing",
                            variable=self.sync_mode_var, value="skip").pack(
            side="left", padx=(0, 15))
        ctk.CTkRadioButton(mode_ctrl, text="Purge & Re-sync",
                            variable=self.sync_mode_var, value="purge").pack(
            side="left", padx=5)

        # --- Bottom section (pack with side="bottom" first to reserve space) ---

        # Action buttons (always visible)
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=10)

        self.preview_btn = ctk.CTkButton(btn_frame, text="Load Preview",
                                          fg_color=CLR_ACCENT, hover_color=CLR_SECONDARY,
                                          command=self._run_preview)
        self.preview_btn.pack(side="left", padx=10)

        self.sync_btn = ctk.CTkButton(btn_frame, text="Start Sync",
                                       fg_color=CLR_PRIMARY, hover_color=CLR_SECONDARY,
                                       command=self._run_sync)
        self.sync_btn.pack(side="left", padx=10)

        self.cancel_btn = ctk.CTkButton(btn_frame, text="Cancel",
                                         fg_color=CLR_DANGER, hover_color=CLR_DANGER_HOVER,
                                         command=self._cancel_sync, state="disabled")
        self.cancel_btn.pack(side="left", padx=10)

        ctk.CTkButton(btn_frame, text="Export Log", width=90,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=self._export_log).pack(side="left", padx=10)

        # --- Main content ---

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(tab, progress_color=CLR_PRIMARY)
        self.progress_bar.pack(fill="x", padx=20, pady=5)
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(tab, text="Ready", anchor="w")
        self.progress_label.pack(fill="x", padx=20)

        # Log output
        self.log_textbox = ctk.CTkTextbox(tab, height=300, state="disabled",
                                           font=FONT_CODE)
        self.log_textbox.pack(fill="both", expand=True, padx=20, pady=(5, 0))

    def _open_date_picker(self, target_var):
        """Open a calendar date picker popup."""
        # Parse current value or default to today
        try:
            parts = target_var.get().strip().split("/")
            cur_day, cur_month, cur_year = int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            today = date.today()
            cur_day, cur_month, cur_year = today.day, today.month, today.year

        picker = ctk.CTkToplevel(self)
        picker.title("Select Date")
        picker.geometry("310x330")
        picker.resizable(False, False)
        picker.grab_set()
        picker.attributes("-topmost", True)

        # State for current displayed month/year
        display_month = [cur_month]
        display_year = [cur_year]

        # Header: << < Month Year > >>
        header = ctk.CTkFrame(picker, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkButton(header, text="<<", width=32, height=28,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=lambda: _change_month(-12)).pack(side="left", padx=1)
        ctk.CTkButton(header, text="<", width=32, height=28,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=lambda: _change_month(-1)).pack(side="left", padx=1)

        month_year_label = ctk.CTkLabel(header, text="", font=FONT_SECTION,
                                         text_color=CLR_PRIMARY)
        month_year_label.pack(side="left", expand=True)

        ctk.CTkButton(header, text=">", width=32, height=28,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=lambda: _change_month(1)).pack(side="right", padx=1)
        ctk.CTkButton(header, text=">>", width=32, height=28,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=lambda: _change_month(12)).pack(side="right", padx=1)

        # Day-of-week headers
        dow_frame = ctk.CTkFrame(picker, fg_color="transparent")
        dow_frame.pack(fill="x", padx=10)
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            ctk.CTkLabel(dow_frame, text=d, width=38, font=FONT_CAPTION,
                          text_color=CLR_SECONDARY).pack(side="left", padx=1)

        # Calendar grid
        cal_frame = ctk.CTkFrame(picker, fg_color="transparent")
        cal_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        # Bottom buttons
        bottom = ctk.CTkFrame(picker, fg_color="transparent")
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(bottom, text="Today", width=70, height=28,
                       fg_color=CLR_ACCENT, hover_color=CLR_SECONDARY,
                       command=lambda: _select(date.today())).pack(side="left", padx=5)
        ctk.CTkButton(bottom, text="Clear", width=70, height=28,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=lambda: _clear()).pack(side="left", padx=5)
        ctk.CTkButton(bottom, text="Cancel", width=70, height=28,
                       fg_color="gray70", hover_color="gray60",
                       command=picker.destroy).pack(side="right", padx=5)

        def _select(d):
            target_var.set(d.strftime("%d/%m/%Y"))
            picker.destroy()

        def _clear():
            target_var.set("")
            picker.destroy()

        def _change_month(delta):
            m = display_month[0] + delta
            y = display_year[0]
            while m > 12:
                m -= 12
                y += 1
            while m < 1:
                m += 12
                y -= 1
            display_month[0] = m
            display_year[0] = y
            _render_calendar()

        def _render_calendar():
            for w in cal_frame.winfo_children():
                w.destroy()

            m, y = display_month[0], display_year[0]
            month_year_label.configure(
                text=f"{calendar.month_name[m]} {y}")

            today = date.today()
            cal = calendar.monthcalendar(y, m)

            for week_row, week in enumerate(cal):
                row_frame = ctk.CTkFrame(cal_frame, fg_color="transparent")
                row_frame.pack(fill="x")
                for day_num in week:
                    if day_num == 0:
                        ctk.CTkLabel(row_frame, text="", width=38, height=32).pack(
                            side="left", padx=1, pady=1)
                    else:
                        d = date(y, m, day_num)
                        is_today = (d == today)
                        is_selected = (day_num == cur_day and m == cur_month
                                       and y == cur_year)

                        if is_selected:
                            fg = CLR_PRIMARY
                            text_clr = "white"
                        elif is_today:
                            fg = CLR_BG_SEC
                            text_clr = "black"
                        else:
                            fg = "transparent"
                            text_clr = "black"

                        btn = ctk.CTkButton(
                            row_frame, text=str(day_num), width=38, height=32,
                            fg_color=fg, text_color=text_clr,
                            hover_color=CLR_BG_HOVER,
                            command=lambda dd=d: _select(dd))
                        btn.pack(side="left", padx=1, pady=1)

        _render_calendar()

    def _init_default_dates(self):
        """Set default date values: Date From = earliest last_synced, Date To = today."""
        # Date To = today
        self.date_to_var.set(date.today().strftime("%d/%m/%Y"))

        # Date From = earliest last_synced across enabled entities
        earliest = None
        for entity in self.config.get_enabled_entities():
            if entity.last_synced:
                try:
                    dt = datetime.fromisoformat(entity.last_synced)
                    if earliest is None or dt < earliest:
                        earliest = dt
                except (ValueError, TypeError):
                    pass
        if earliest:
            self.date_from_var.set(earliest.strftime("%d/%m/%Y"))

    def _toggle_date_filter(self):
        """Enable/disable date range fields based on checkbox."""
        enabled = self.date_filter_var.get()
        state = "normal" if enabled else "disabled"

        lbl_color = "gray10" if enabled else "gray"
        self._date_from_label.configure(text_color=lbl_color)
        self._date_from_display.configure(state=state)
        self._date_from_pick_btn.configure(state=state)
        self._date_to_label.configure(text_color=lbl_color)
        self._date_to_display.configure(state=state)
        self._date_to_pick_btn.configure(state=state)

        if not enabled:
            self.date_from_var.set("")
            self.date_to_var.set("")

    def _parse_date(self, val: str):
        """Convert DD/MM/YYYY to YYYY-MM-DD for SQL, or return None if empty."""
        if not val or not val.strip():
            return None
        parts = val.strip().split("/")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return val  # fallback: pass as-is

    def _update_master_summary(self):
        """Update master data summary label."""
        selected = [self._master_labels[k] for k in self._master_labels if self.master_vars[k].get()]
        if len(selected) == len(self._master_labels):
            text = "All selected"
        elif selected:
            text = ", ".join(selected)
        else:
            text = "(none)"
        self._master_summary_label.configure(text=text)

    def _update_txn_summary(self):
        """Update transaction data summary label."""
        selected = [self._txn_labels[m] for m in IMPORT_ORDER if self.module_vars[m].get()]
        if len(selected) == len(IMPORT_ORDER):
            text = "All selected"
        elif selected:
            text = ", ".join(selected)
        else:
            text = "(none)"
        self._txn_summary_label.configure(text=text)

    def _open_master_data_popup(self):
        """Open popup for master data import selection."""
        popup = ctk.CTkToplevel(self)
        popup.title("Master Data Import")
        h = max(180, 100 + len(self._master_labels) * 30)
        popup.geometry(f"300x{h}")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        # Center on parent
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 300) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        popup.geometry(f"+{x}+{y}")

        ctk.CTkLabel(popup, text="Select Master Data to Import",
                      font=FONT_SECTION).pack(
            padx=15, pady=(15, 10), anchor="w")

        for key in self._master_labels:
            ctk.CTkCheckBox(popup, text=self._master_labels[key],
                             variable=self.master_vars[key]).pack(
                padx=25, pady=2, anchor="w")

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=(10, 15))

        ctk.CTkButton(btn_frame, text="Select All", width=80,
                       fg_color=CLR_ACCENT, hover_color=CLR_SECONDARY,
                       command=lambda: [v.set(True) for v in self.master_vars.values()]).pack(
            side="left", padx=5)

        ctk.CTkButton(btn_frame, text="Deselect All", width=80,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=lambda: [v.set(False) for v in self.master_vars.values()]).pack(
            side="left", padx=5)

        ctk.CTkButton(btn_frame, text="OK", width=80,
                       fg_color=CLR_PRIMARY, hover_color=CLR_SECONDARY,
                       command=lambda: (self._update_master_summary(), popup.destroy())).pack(
            side="left", padx=5)

    def _open_txn_data_popup(self):
        """Open popup for transaction data import selection."""
        popup = ctk.CTkToplevel(self)
        popup.title("Transaction Data Import")
        popup.geometry("300x320")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        # Center on parent
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 300) // 2
        y = self.winfo_y() + (self.winfo_height() - 320) // 2
        popup.geometry(f"+{x}+{y}")

        ctk.CTkLabel(popup, text="Select Transactions to Import",
                      font=FONT_SECTION).pack(
            padx=15, pady=(15, 10), anchor="w")

        for mod in IMPORT_ORDER:
            ctk.CTkCheckBox(popup, text=self._txn_labels.get(mod, mod),
                             variable=self.module_vars[mod]).pack(
                padx=25, pady=2, anchor="w")

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=(10, 15))

        ctk.CTkButton(btn_frame, text="Select All", width=80,
                       fg_color=CLR_ACCENT, hover_color=CLR_SECONDARY,
                       command=lambda: [v.set(True) for v in self.module_vars.values()]).pack(
            side="left", padx=5)

        ctk.CTkButton(btn_frame, text="Deselect All", width=80,
                       fg_color=CLR_SECONDARY, hover_color=CLR_PRIMARY,
                       command=lambda: [v.set(False) for v in self.module_vars.values()]).pack(
            side="left", padx=5)

        ctk.CTkButton(btn_frame, text="OK", width=80,
                       fg_color=CLR_PRIMARY, hover_color=CLR_SECONDARY,
                       command=lambda: (self._update_txn_summary(), popup.destroy())).pack(
            side="left", padx=5)

    def _get_selected_modules(self) -> list:
        return [mod for mod, var in self.module_vars.items() if var.get()]

    def _get_enabled_entities(self) -> list:
        return self.config.get_enabled_entities()

    def _log_to_ui(self, level, message):
        """Thread-safe log callback for the UI textbox."""
        def _append():
            self.log_textbox.configure(state="normal")
            tag = ""
            prefix = ""
            if level == "ERROR":
                prefix = "[ERROR] "
            elif level == "WARNING":
                prefix = "[WARN]  "
            elif level == "SUCCESS":
                prefix = "[OK]    "
            else:
                prefix = "[INFO]  "
            self.log_textbox.insert("end", f"{prefix}{message}\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
        self.after(0, _append)

    def _progress_callback(self, current, total, message):
        """Thread-safe progress update."""
        def _update():
            if total > 0:
                self.progress_bar.set(current / total)
            self.progress_label.configure(text=f"{message} ({current}/{total})")
        self.after(0, _update)

    def _set_syncing(self, is_syncing: bool):
        """Toggle UI state during sync."""
        state = "disabled" if is_syncing else "normal"
        self.preview_btn.configure(state=state)
        self.sync_btn.configure(state=state)
        self.cancel_btn.configure(state="normal" if is_syncing else "disabled")

    def _clear_log(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def _export_log(self):
        """Export the current log textbox content to a text file."""
        content = self.log_textbox.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Export Log", "No log content to export.")
            return

        default_name = f"sync_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Export Log", f"Log exported to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    # ------------------------------------------------------------------
    # About / What's New
    # ------------------------------------------------------------------
    def _show_about(self):
        """Show About dialog with version info."""
        messagebox.showinfo(
            "About",
            f"{APP_NAME}\n"
            f"Version: {APP_VERSION} (Build {APP_BUILD_NUMBER})\n\n"
            f"SQL Account Consolidation Sync Tool\n"
            f"Powered by SQL Account SDK"
        )

    def _show_whats_new(self):
        """Show What's New dialog with changelog."""
        changelog_path = os.path.join(os.path.dirname(__file__), "CHANGELOG.md")
        try:
            with open(changelog_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            content = "No changelog available."

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"What's New — {APP_NAME}")
        dialog.geometry("520x420")
        dialog.resizable(True, True)
        dialog.transient(self)
        dialog.grab_set()

        textbox = ctk.CTkTextbox(dialog, font=FONT_CODE, wrap="word")
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        textbox.insert("1.0", content)
        textbox.configure(state="disabled")

        ctk.CTkButton(dialog, text="Close", fg_color=CLR_PRIMARY,
                       hover_color=CLR_SECONDARY,
                       command=dialog.destroy).pack(pady=(0, 10))

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _run_preview(self):
        entities = self._get_enabled_entities()
        modules = self._get_selected_modules()

        if not entities:
            messagebox.showwarning("No Entities", "No enabled entities to preview.")
            return
        if not modules:
            messagebox.showwarning("No Modules", "Please select at least one module.")
            return

        is_purge = self.sync_mode_var.get() == "purge"

        self._clear_log()
        self._set_syncing(True)

        def _preview_thread():
            pythoncom.CoInitialize()
            try:
                logger = SyncLogger(log_callback=self._log_to_ui)
                engine = SyncEngine(self.config, logger, self._progress_callback)
                date_from = self._parse_date(self.date_from_var.get())
                date_to = self._parse_date(self.date_to_var.get())

                if is_purge:
                    logger.info("Starting comparison preview (Purge & Re-sync)...")
                    results = engine.compare_documents(
                        entities, modules, date_from, date_to)

                    logger.info("=" * 50)
                    logger.info("COMPARISON RESULTS")
                    logger.info("=" * 50)
                    for r in results:
                        logger.info(f"Entity: {r['entity_name']} (Prefix: {r['prefix']})")
                        for mod, data in r["modules"].items():
                            matched = (data["source_count"]
                                       - len(data["new"]) - len(data["changed"]))
                            logger.info(f"  {mod}: {data['source_count']} in source, "
                                        f"{data['consol_count']} in consol")
                            if matched > 0:
                                logger.info(f"    Matched: {matched}")
                            if data["new"]:
                                logger.info(f"    New in source: {len(data['new'])}")
                            if data["changed"]:
                                logger.info(f"    Changed: {len(data['changed'])}")
                                for c in data["changed"][:5]:
                                    logger.info(f"      {c['doc_no']}: {c['diffs']}")
                                if len(data["changed"]) > 5:
                                    logger.info(f"      ... and {len(data['changed'])-5} more")
                            if data["deleted"]:
                                logger.info(f"    Deleted from source: {len(data['deleted'])}")
                else:
                    logger.info("Starting preview (dry run)...")
                    results = engine.preview(
                        entities, modules, date_from, date_to)

                    logger.info("=" * 50)
                    logger.info("PREVIEW RESULTS")
                    logger.info("=" * 50)
                    for r in results:
                        logger.info(f"Entity: {r.entity_name} (Prefix: {r.prefix})")
                        logger.info(f"  Customers: {r.customer_count}")
                        for mod, count in r.doc_counts.items():
                            status = str(count) if count >= 0 else "ERROR"
                            logger.info(f"  {mod}: {status}")

                self.after(0, lambda: self._set_syncing(False))
                self.after(0, lambda: self.progress_label.configure(text="Preview complete"))
            finally:
                logger.close()
                pythoncom.CoUninitialize()

        self._sync_thread = threading.Thread(target=_preview_thread, daemon=True)
        self._sync_thread.start()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def _run_sync(self):
        entities = self._get_enabled_entities()
        modules = self._get_selected_modules()

        if not entities:
            messagebox.showwarning("No Entities", "No enabled entities to sync.")
            return
        if not modules:
            messagebox.showwarning("No Modules", "Please select at least one module.")
            return

        is_purge = self.sync_mode_var.get() == "purge"

        if is_purge:
            # Reverse confirmation — Yes = cancel (safe default)
            if messagebox.askyesno(
                "Purge & Re-sync",
                f"Purge & Re-sync will DELETE and re-import all documents "
                f"for {len(entities)} entity(ies) in the selected date range.\n\n"
                "This may take longer than expected.\n\n"
                "IMPORTANT: Please ensure you have backed up the consolidation database before proceeding.\n\n"
                "Do you want to CANCEL the operation?",
                default="yes"
            ):
                return  # User chose Yes = cancel
        else:
            if not messagebox.askyesno(
                "Confirm Sync",
                f"Sync {len(entities)} entity(ies) with modules: {', '.join(modules)}?\n\n"
                "IMPORTANT: Please ensure you have backed up the consolidation database."
            ):
                return

        self._clear_log()
        self._set_syncing(True)

        def _sync_thread():
            pythoncom.CoInitialize()
            try:
                logger = SyncLogger(log_callback=self._log_to_ui)
                mode_label = "Purge & Re-sync" if is_purge else "sync"
                logger.info(f"Starting {mode_label}...")

                self.sync_engine = SyncEngine(self.config, logger, self._progress_callback)
                import time as _time
                sync_start = _time.time()
                results = self.sync_engine.sync(
                    entities, modules,
                    date_from=self._parse_date(self.date_from_var.get()),
                    date_to=self._parse_date(self.date_to_var.get()),
                    sync_customers=self.sync_cust_var.get(),
                    purge_resync=is_purge,
                )
                total_duration = _format_duration(_time.time() - sync_start)

                # Display results summary
                logger.info("=" * 50)
                logger.info("SYNC RESULTS SUMMARY")
                logger.info("=" * 50)
                for r in results:
                    logger.info(f"Entity: {r.entity_name} (Prefix: {r.prefix})")
                    logger.info(f"  Customers: {r.customers_synced} synced, "
                                f"{r.customers_skipped} skipped, {r.customers_failed} failed")
                    for mod in IMPORT_ORDER:
                        s = r.docs_synced.get(mod, 0)
                        sk = r.docs_skipped.get(mod, 0)
                        f = r.docs_failed.get(mod, 0)
                        if s or sk or f:
                            logger.info(f"  {mod}: {s} synced, {sk} skipped, {f} failed")
                    if r.errors:
                        for err in r.errors:
                            logger.error(f"  Error: {err}")

                logger.info(f"Total sync duration: {total_duration}")

                self.after(0, lambda: self._set_syncing(False))
                self.after(0, lambda: self.progress_label.configure(text="Sync complete"))
                self.after(0, lambda: self._refresh_entity_list())
            finally:
                logger.close()
                pythoncom.CoUninitialize()

        self._sync_thread = threading.Thread(target=_sync_thread, daemon=True)
        self._sync_thread.start()

    def _cancel_sync(self):
        if self.sync_engine:
            self.sync_engine.cancel()
            self.progress_label.configure(text="Cancelling...")

    # ==================================================================
    # Helpers
    # ==================================================================
    def _fetch_company_categories(self):
        """Fetch Company Categories from the consol DB via Firebird direct connection."""
        consol = self.config.consol_db
        if not consol.fb_path:
            # Fallback to SDK if no Firebird path configured
            if consol.dcf_path and consol.db_name:
                from consol_writer import fetch_company_categories
                self._company_categories = fetch_company_categories(consol)
                return self._company_categories
            return []

        conn = None
        try:
            conn = fdb.connect(
                host=consol.fb_host,
                database=consol.fb_path,
                user=consol.fb_user,
                password=consol.fb_password,
                charset="UTF8",
            )
            cur = conn.cursor()
            cur.execute("SELECT CODE, DESCRIPTION FROM COMPANYCATEGORY WHERE ISACTIVE=TRUE ORDER BY CODE")
            self._company_categories = []
            for row in cur.fetchall():
                code = (row[0] or "").strip()
                desc = (row[1] or "").strip()
                if code:
                    self._company_categories.append({"code": code, "description": desc})
            cur.close()
        except Exception as e:
            messagebox.showerror("Connection Failed",
                                 f"Could not read categories from consol DB.\n\n{e}")
            self._company_categories = []
        finally:
            if conn:
                conn.close()

        return self._company_categories

    def _browse_file(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _create_info_icon(self, parent, tooltip_text):
        """Create a hoverable ℹ info icon with native OS tooltip."""
        import tkinter as tk
        icon = ctk.CTkLabel(parent, text=" ℹ", font=FONT_ICON,
                             text_color=CLR_ACCENT, cursor="hand2")
        icon.pack(side="left", padx=(2, 0))

        # Use native tk tooltip (no floating window issues)
        class _NativeTooltip:
            def __init__(self, widget, text):
                self._widget = widget
                self._text = text
                self._tw = None
                self._after_id = None
                widget.bind("<Enter>", self._on_enter)
                widget.bind("<Leave>", self._on_leave)

            def _on_enter(self, event):
                self._after_id = self._widget.after(400, self._show)

            def _on_leave(self, event):
                if self._after_id:
                    self._widget.after_cancel(self._after_id)
                    self._after_id = None
                self._hide()

            def _show(self):
                self._after_id = None
                self._hide()
                x = self._widget.winfo_rootx() + self._widget.winfo_width() + 4
                y = self._widget.winfo_rooty()
                self._tw = tk.Toplevel(self._widget)
                self._tw.wm_overrideredirect(True)
                self._tw.wm_geometry(f"+{x}+{y}")
                self._tw.attributes("-topmost", True)
                label = tk.Label(self._tw, text=self._text, justify="left",
                                 background="#FFFDE7", foreground="#333333",
                                 relief="solid", borderwidth=1,
                                 font=FONT_TOOLTIP, padx=8, pady=4,
                                 wraplength=300)
                label.pack()

            def _hide(self):
                if self._tw:
                    self._tw.destroy()
                    self._tw = None

        _NativeTooltip(icon, tooltip_text)
