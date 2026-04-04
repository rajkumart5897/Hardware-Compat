"""
config.py — Persistent settings for hardware-compat.

Stored at ~/.config/hardware-compat/settings.json
All values have safe defaults so the tool works out-of-the-box
with zero configuration.
"""

import json
import os
from pathlib import Path

CONFIG_DIR  = Path.home() / ".config" / "hardware-compat"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    # Launch behaviour
    "default_mode":        "gui",       # "gui" | "cli"
    "gui_port":            7474,
    "auto_open_browser":   True,

    # GUI behaviour
    "refresh_interval_s":  10,          # seconds between live-monitor polls; 0 = off
    "scan_interval_s":     0,           # seconds between full rescans; 0 = manual only
    "theme":               "auto",      # "auto" | "light" | "dark"

    # Display filters
    "temp_unit":           "C",         # "C" | "F"
    "severity_filter":     "ALL",       # "ALL" | "HIGH" | "MEDIUM"
    "hidden_categories":   [],          # list of category strings to hide

    # Alert thresholds
    "alert_cpu_temp_c":    85,          # warn if any CPU core exceeds this
    "alert_disk_temp_c":   55,
    "alert_ram_pct":       90,          # warn if RAM usage exceeds this %
    "alert_cpu_pct":       95,

    # Export
    "export_dir":          str(Path.home() / "Downloads"),

    # CLI behaviour (when default_mode = "cli")
    "cli_auto_apply":      False,       # skip the interactive fix prompt

    "shutdown_on_idle": True,   # stop server when browser tab closes
    "idle_timeout_s":   30,     # seconds of no ping before shutdown
}


def load() -> dict:
    """Load settings, merging with defaults for any missing keys."""
    if not CONFIG_FILE.exists():
        return dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(saved)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save(settings: dict) -> bool:
    """Persist settings. Returns True on success."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        merged = dict(DEFAULTS)
        merged.update(settings)
        with open(CONFIG_FILE, "w") as f:
            json.dump(merged, f, indent=2)
        return True
    except OSError:
        return False


def get(key: str):
    """Convenience: load and return a single key."""
    return load().get(key, DEFAULTS.get(key))
