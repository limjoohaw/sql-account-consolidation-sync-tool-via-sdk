"""Configuration manager for entity DB connections and app settings."""

import os
import sys
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional

# In PyInstaller bundle, config.json lives next to the .exe (not inside _internal/)
if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_APP_DIR, "config.json")
_config_lock = threading.Lock()


@dataclass
class ConsolDBConfig:
    dcf_path: str = ""
    db_name: str = ""
    username: str = "ADMIN"
    password: str = "ADMIN"
    # Firebird direct connection (for fast reads without SDK)
    fb_host: str = "localhost"
    fb_path: str = ""             # Full .FDB file path for fdb driver
    fb_user: str = "SYSDBA"
    fb_password: str = "masterkey"


@dataclass
class EntityConfig:
    # User-defined
    customer_code_prefix: str = "300-"
    # Firebird direct connection (for source reading)
    fb_host: str = "localhost"
    fb_path: str = ""                 # Full .FDB file path for fdb driver
    fb_user: str = "SYSDBA"
    fb_password: str = "masterkey"
    # Auto-read from SY_PROFILE at sync time
    name: str = ""                    # SY_PROFILE.COMPANYNAME (auto-read)
    remark: str = ""                  # SY_PROFILE.REMARK (auto-read, for identification)
    prefix: str = ""                  # SY_PROFILE.ALIAS (Entity Prefix)
    # Per-customer company category mapping (original customer code → category code)
    customer_category_map: dict = field(default_factory=dict)
    # Sync tracking
    last_synced: Optional[str] = None
    enabled: bool = True


@dataclass
class AppConfig:
    consol_db: ConsolDBConfig = field(default_factory=ConsolDBConfig)
    entities: list = field(default_factory=list)
    last_sync_selection: list = field(default_factory=list)  # entity indices last selected in Sync tab

    def add_entity(self, entity: EntityConfig):
        self.entities.append(entity)

    def remove_entity(self, index: int):
        if 0 <= index < len(self.entities):
            self.entities.pop(index)

    def get_enabled_entities(self) -> list:
        return [e for e in self.entities if e.enabled]


def load_config() -> AppConfig:
    """Load configuration from JSON file."""
    with _config_lock:
        if not os.path.exists(CONFIG_FILE):
            return AppConfig()

        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            import logging
            logging.warning(f"config.json is malformed, using defaults: {e}")
            return AppConfig()

        config = AppConfig()
        # Load consol DB config
        if "consol_db" in data:
            config.consol_db = ConsolDBConfig(**data["consol_db"])

        # Load entities
        valid_fields = {f for f in EntityConfig.__dataclass_fields__}
        for ent_data in data.get("entities", []):
            filtered = {k: v for k, v in ent_data.items() if k in valid_fields}
            config.entities.append(EntityConfig(**filtered))

        config.last_sync_selection = data.get("last_sync_selection", [])

        return config


def save_config(config: AppConfig):
    """Save configuration to JSON file."""
    with _config_lock:
        data = {
            "consol_db": asdict(config.consol_db),
            "entities": [asdict(e) for e in config.entities],
            "last_sync_selection": config.last_sync_selection,
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)
