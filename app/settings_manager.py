"""
Settings persistence manager.
Saves/loads application configuration to a JSON file in the app directory.
Settings survive application restarts.
"""

import json
import os
from typing import List, Optional
from app.data_model import LimitLine, Project

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "settings.json")


def _default_settings() -> dict:
    return {
        "total_pairs": 8,
        "display_freq_start_hz": 100000.0,
        "display_freq_stop_hz": 500000000.0,
        "visa_address": "",
        "save_folder": "",
        "sweep_points": 1001,
        "power_sum_enabled": True,
        "worst_case_enabled": False,
        "limit_lines": [],
    }


def load_settings() -> dict:
    """Load settings from JSON file. Returns defaults if file doesn't exist."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                defaults = _default_settings()
                defaults.update(data)
                return defaults
    except Exception:
        pass
    return _default_settings()


def save_settings(settings: dict):
    """Save settings to JSON file."""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Failed to save settings: {e}")


def settings_to_project(settings: dict, project: Project):
    """Apply saved settings to a project."""
    project.total_pairs = settings.get("total_pairs", 8)
    project.display_freq_start = settings.get("display_freq_start_hz", 100000.0)
    project.display_freq_stop = settings.get("display_freq_stop_hz", 500000000.0)
    project.limit_lines = []
    for ll in settings.get("limit_lines", []):
        project.limit_lines.append(LimitLine(
            name=ll.get("name", "未命名"),
            color=ll.get("color", "red"),
            visible=ll.get("visible", True),
            points=[(p[0], p[1]) for p in ll.get("points", [])],
        ))


def project_to_settings(project: Project) -> dict:
    """Extract settings from a project."""
    return {
        "total_pairs": project.total_pairs,
        "display_freq_start_hz": project.display_freq_start,
        "display_freq_stop_hz": project.display_freq_stop,
        "limit_lines": [
            {
                "name": ll.name,
                "color": ll.color,
                "visible": ll.visible,
                "points": ll.points,
            }
            for ll in project.limit_lines
        ],
    }
