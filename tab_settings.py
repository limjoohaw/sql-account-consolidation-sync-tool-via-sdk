"""Settings tab — Consolidation DB configuration."""

import fdb
from nicegui import ui, run
from config import ConsolDBConfig, save_config
from shared import CLR_PRIMARY, CLR_ACCENT


def build_settings_tab(config):
    """Build the Settings tab UI."""

    consol = config.consol_db

    with ui.card().classes('w-full'):
        ui.label('Consolidation Database').classes(
            'text-lg font-bold').style(f'color: {CLR_PRIMARY}')

        with ui.grid(columns=2).classes('w-full gap-y-2 gap-x-4 items-center'):
            # FDB Path
            ui.label('FDB Path:').classes('font-bold')
            fb_path = ui.input(value=consol.fb_path,
                               placeholder='e.g. C:\\eStream\\SQLAccounting\\DB\\CONSOLSOA.FDB'
                               ).classes('w-96').tooltip(
                'Full path to the consolidation .FDB file')

            # Firebird Host
            ui.label('Firebird Host:').classes('font-bold')
            fb_host = ui.input(value=consol.fb_host,
                               placeholder='localhost (or server IP)').classes('w-96')

            # Firebird User
            ui.label('Firebird User:').classes('font-bold')
            fb_user = ui.input(value=consol.fb_user,
                               placeholder='SYSDBA').classes('w-96')

            # Firebird Password
            ui.label('Firebird Password:').classes('font-bold')
            fb_pass = ui.input(value=consol.fb_password,
                               placeholder='masterkey', password=True,
                               password_toggle_button=True).classes('w-96')

            # DCF Path
            ui.label('DCF Path:').classes('font-bold')
            dcf_path = ui.input(value=consol.dcf_path,
                                placeholder='e.g. C:\\eStream\\SQLAccounting\\Share\\Default.DCF'
                                ).classes('w-96').tooltip(
                'SQL Account DCF file path — used for SDK write operations during sync')

            # DB Name
            ui.label('DB Name:').classes('font-bold')
            db_name = ui.input(value=consol.db_name,
                               placeholder='Filename only, e.g. CONSOLSOA.FDB (NOT full path)'
                               ).classes('w-96').tooltip(
                'Filename only (NOT full path) — used for SDK write operations during sync')

            # SQL Acc Username
            ui.label('SQL Acc Username:').classes('font-bold')
            sql_user = ui.input(value=consol.username,
                                placeholder='ADMIN').classes('w-96')

            # SQL Acc Password
            ui.label('SQL Acc Password:').classes('font-bold')
            sql_pass = ui.input(value=consol.password,
                                placeholder='ADMIN', password=True,
                                password_toggle_button=True).classes('w-96')

    with ui.row().classes('justify-center mt-4'):
        ui.button('Test Connection',
                  on_click=lambda: test_connection(
                      dcf_path.value, db_name.value,
                      sql_user.value, sql_pass.value),
                  color=CLR_ACCENT)
        ui.button('Save Settings',
                  on_click=lambda: save_settings(
                      config, fb_path.value, fb_host.value,
                      fb_user.value, fb_pass.value,
                      dcf_path.value, db_name.value,
                      sql_user.value, sql_pass.value),
                  color=CLR_PRIMARY)


def save_settings(config, fb_path, fb_host, fb_user, fb_pass,
                   dcf_path, db_name, sql_user, sql_pass):
    """Save consolidation DB settings."""
    config.consol_db = ConsolDBConfig(
        dcf_path=dcf_path,
        db_name=db_name,
        username=sql_user,
        password=sql_pass,
        fb_host=fb_host,
        fb_path=fb_path,
        fb_user=fb_user,
        fb_password=fb_pass,
    )
    save_config(config)
    ui.notify('Consolidation DB settings saved.', type='positive')


async def test_connection(dcf_path, db_name, sql_user, sql_pass):
    """Test SDK login to the consolidation database."""
    dcf = (dcf_path or '').strip()
    db = (db_name or '').strip()
    user = (sql_user or '').strip()
    pwd = (sql_pass or '').strip()

    if not dcf or not db:
        ui.notify('Please fill in DCF Path and DB Name.', type='warning')
        return

    def _test():
        import pythoncom
        pythoncom.CoInitialize()
        try:
            import win32com.client
            app = win32com.client.Dispatch("SQLAcc.BizApp")
            if app.IsLogin:
                app.Logout()
            app.Login(user, pwd, dcf, db)

            if not app.IsLogin:
                return None, "Login failed. Please check your username/password."

            try:
                ds = app.DBManager.NewDataSet(
                    "SELECT FIRST 1 COMPANYNAME FROM SY_PROFILE")
                try:
                    company = ""
                    if ds.RecordCount > 0:
                        company = ds.FindField("COMPANYNAME").AsString
                finally:
                    ds.Close()
                app.Logout()
                return company, None
            except Exception as e:
                app.Logout()
                return None, str(e)
        except Exception as e:
            return None, str(e)
        finally:
            pythoncom.CoUninitialize()

    company, error = await run.io_bound(_test)

    if error:
        ui.notify(f'Connection failed: {error}', type='negative', multi_line=True)
    else:
        msg = f'Connected successfully! Database: {db}'
        if company:
            msg += f' | Company: {company}'
        ui.notify(msg, type='positive')
