import json
from pathlib import Path
import os

APP_NAME = "DuckAIWrapper"
CONFIG_FILENAME = "settings.json"

def get_config_dir() -> Path:
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        return Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME

def ensure_config_dir() -> Path:
    d = get_config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d

def settings_path() -> Path:
    return ensure_config_dir() / CONFIG_FILENAME

DEFAULTS = {
    "start_url": "https://duck.ai",
    "width": 1200,
    "height": 800,
    "x": None,
    "y": None,
    "autostart": False
}

def load_settings() -> dict:
    p = settings_path()
    if not p.exists():
        return DEFAULTS.copy()
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return DEFAULTS.copy()
    out = DEFAULTS.copy()
    out.update({k: data.get(k, DEFAULTS[k]) for k in DEFAULTS})
    return out

def save_settings(d: dict) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
1