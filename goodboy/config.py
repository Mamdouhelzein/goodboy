"""Paths and user configuration for goodboy."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEFAULT_SOURCES = ["anthropics/skills", "Mamdouhelzein/goodboy/skills"]


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


def home_dir() -> Path:
    """Where repos, the index and installed skills live."""
    if os.environ.get("GOODBOY_HOME"):
        return Path(os.environ["GOODBOY_HOME"])
    return _xdg("XDG_DATA_HOME", ".local/share") / "goodboy"


def config_path() -> Path:
    if os.environ.get("GOODBOY_HOME"):
        return Path(os.environ["GOODBOY_HOME"]) / "config.json"
    return _xdg("XDG_CONFIG_HOME", ".config") / "goodboy" / "config.json"


def repos_dir() -> Path:
    return home_dir() / "repos"


def installed_dir() -> Path:
    return home_dir() / "skills"


def index_path() -> Path:
    return home_dir() / "index.json"


@dataclass
class Config:
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    index_ttl_hours: float = 24.0

    @classmethod
    def load(cls) -> "Config":
        p = config_path()
        cfg = cls()
        if p.exists():
            data = json.loads(p.read_text())
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        return cfg

    def save(self) -> None:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2) + "\n")
