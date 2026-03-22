"""Human-readable logging with error translation for SDK operations."""

import logging
import datetime
import os
import sys
from typing import Optional

# In PyInstaller bundle, logs/ lives next to the .exe (not inside _internal/)
if getattr(sys, 'frozen', False):
    LOG_DIR = os.path.join(os.path.dirname(sys.executable), "logs")
else:
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# Common COM/SDK error translations
ERROR_TRANSLATIONS = {
    "80040154": "SQL Account SDK is not registered. Please reinstall SQL Accounting.",
    "80040005": "Access denied. Check your login credentials.",
    "800401f3": "COM object is invalid. Ensure SQL Accounting is running.",
    "deadlock": "Database is locked by another user. Please try again.",
    "lock conflict": "Record is locked by another session. Wait and retry.",
    "connection rejected": "Cannot connect to database. Check if Firebird service is running.",
    "unavailable database": "Database file not found or inaccessible. Check file path.",
    "your file is not a valid": "Invalid database file. Check the .FDB file path.",
    "i/o error": "File I/O error. Check if the database file path is correct and accessible.",
    "login": "Login failed. Check username/password.",
}


def _translate_error(error_msg: str) -> str:
    """Translate technical errors to human-readable messages."""
    lower_msg = error_msg.lower()
    for key, translation in ERROR_TRANSLATIONS.items():
        if key.lower() in lower_msg:
            return f"{translation}\n  Technical: {error_msg}"
    return error_msg


def cleanup_old_logs(keep=50):
    """Delete old log files, keeping the most recent `keep` files."""
    if not os.path.isdir(LOG_DIR):
        return
    log_files = sorted(
        [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR) if f.endswith(".log")],
        key=os.path.getmtime,
        reverse=True,
    )
    for old_file in log_files[keep:]:
        try:
            os.remove(old_file)
        except OSError:
            pass


class SyncLogger:
    """Logger that writes to both file and provides callbacks for UI updates."""

    def __init__(self, log_callback=None):
        self.log_callback = log_callback  # Function to call for UI updates
        self._entries = []

        # Ensure log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)

        # File logger — use microseconds to avoid timestamp collisions
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_file = os.path.join(LOG_DIR, f"sync_{timestamp}.log")

        self._file_logger = logging.getLogger(f"sync_{timestamp}")
        self._file_logger.setLevel(logging.DEBUG)
        # Clear any existing handlers (getLogger caches by name)
        self._file_logger.handlers.clear()
        self._handler = logging.FileHandler(log_file, encoding="utf-8")
        self._handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self._file_logger.addHandler(self._handler)

    def info(self, message: str):
        self._log("INFO", message)

    def success(self, message: str):
        self._log("SUCCESS", message)

    def warning(self, message: str):
        self._log("WARNING", message)

    def error(self, message: str, exception: Optional[Exception] = None):
        if exception:
            translated = _translate_error(str(exception))
            message = f"{message}: {translated}"
        self._log("ERROR", message)

    def _log(self, level: str, message: str):
        entry = f"[{level}] {message}"
        self._entries.append(entry)

        # File logging
        log_level = getattr(logging, level if level != "SUCCESS" else "INFO")
        self._file_logger.log(log_level, message)

        # UI callback
        if self.log_callback:
            self.log_callback(level, message)

    def get_entries(self) -> list:
        return list(self._entries)

    def close(self):
        """Close file handler to release log file lock."""
        if self._handler:
            self._handler.close()
            self._file_logger.removeHandler(self._handler)
            self._handler = None
