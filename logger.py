"""Human-readable logging with error translation for SDK operations."""

import logging
import datetime
import os
from typing import Optional

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


class SyncLogger:
    """Logger that writes to both file and provides callbacks for UI updates."""

    def __init__(self, log_callback=None):
        self.log_callback = log_callback  # Function to call for UI updates
        self._entries = []

        # Ensure log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)

        # File logger
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, f"sync_{timestamp}.log")

        self._file_logger = logging.getLogger(f"sync_{timestamp}")
        self._file_logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self._file_logger.addHandler(handler)

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
