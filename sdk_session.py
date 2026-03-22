"""SDK Session Manager with strict license protection.

Every SDK session uses try...finally to guarantee Logout() is called,
even if the sync operation fails, to release concurrent user licenses.

CRITICAL: The SDK COM object (SQLAcc.BizApp) is a shared singleton.
If SQL Account is already open on the PC, Dispatch() returns the
existing instance. We must logout first, then login to our target DB,
and verify the connection before proceeding.
"""

import win32com.client
from config import ConsolDBConfig
from logger import SyncLogger


class SDKSessionError(Exception):
    """Raised when SDK session validation fails."""
    pass


class SDKSession:
    """Context manager for SQL Account SDK COM sessions."""

    def __init__(self, dcf_path: str, db_name: str,
                 username: str = "ADMIN", password: str = "ADMIN",
                 logger: SyncLogger = None,
                 verify_db: str = None):
        self.dcf_path = dcf_path
        self.db_name = db_name
        self.username = username
        self.password = password
        self.logger = logger
        self.verify_db = verify_db  # If set, verify connected DB matches this name
        self.app = None

    def __enter__(self):
        self.app = win32com.client.Dispatch("SQLAcc.BizApp")

        # SDK COM is a singleton - if already logged in, must logout first
        if self.app.IsLogin:
            if self.logger:
                self.logger.warning(
                    "SQL Account is already logged in. "
                    "Logging out before connecting to target DB..."
                )
            self.app.Logout()

        # Login to target DB
        self.app.Login(self.username, self.password, self.dcf_path, self.db_name)

        # SAFETY: Verify we're connected to the correct database
        if self.verify_db:
            self._verify_connected_db()

        if self.logger:
            self.logger.info(f"Logged in to {self.db_name}")
        return self.app

    def _verify_connected_db(self):
        """Verify the SDK is actually connected to the expected database.

        Queries SY_PROFILE and checks the FDB filename to prevent
        accidentally writing to the wrong database.
        """
        ds = None
        try:
            # Check the actual connected database file
            ds = self.app.DBManager.NewDataSet(
                "SELECT MON$DATABASE_NAME FROM MON$DATABASE"
            )
            if ds.RecordCount > 0:
                connected_path = ds.FindField("MON$DATABASE_NAME").AsString
                connected_file = connected_path.split("\\")[-1].split("/")[-1].upper()
                expected_file = self.verify_db.upper()

                if connected_file != expected_file:
                    # CRITICAL: Wrong database! Abort immediately
                    self.app.Logout()
                    self.app = None
                    raise SDKSessionError(
                        f"DATABASE MISMATCH! Expected '{self.verify_db}' "
                        f"but connected to '{connected_file}' ({connected_path}). "
                        f"Aborting to prevent data corruption. "
                        f"Please close SQL Account and try again."
                    )

                if self.logger:
                    self.logger.info(f"Verified connected DB: {connected_file}")
        except SDKSessionError:
            raise  # Re-raise our own error
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not verify database (non-fatal): {e}")
        finally:
            if ds:
                try:
                    ds.Close()
                except Exception:
                    pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.app and self.app.IsLogin:
                self.app.Logout()
                if self.logger:
                    self.logger.info(f"Logged out from {self.db_name}")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error during logout: {e}")
        finally:
            self.app = None
        return False  # Do not suppress exceptions


def open_consol_session(consol: ConsolDBConfig, logger: SyncLogger = None) -> SDKSession:
    """Create an SDK session for the consolidation database."""
    return SDKSession(
        dcf_path=consol.dcf_path,
        db_name=consol.db_name,
        username=consol.username,
        password=consol.password,
        logger=logger,
        verify_db=consol.db_name,  # CRITICAL: Verify we're writing to the right DB
    )
