"""Configuration management for ChemSync."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".chemsync"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    api_url: str = ""
    api_key: str = ""
    category_id: int = 17
    last_mapping_profile: str = ""
    last_csv_path: str = ""
    canread_base: int = 30
    canwrite_base: int = 20

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(
                {
                    "api_url": self.api_url,
                    "api_key": self.api_key,
                    "category_id": self.category_id,
                    "last_mapping_profile": self.last_mapping_profile,
                    "last_csv_path": self.last_csv_path,
                    "canread_base": self.canread_base,
                    "canwrite_base": self.canwrite_base,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> AppConfig:
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (json.JSONDecodeError, TypeError):
            return cls()
