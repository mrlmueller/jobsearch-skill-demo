"""Minimaler .env-Loader (ROOT/.env), keine Zusatz-Dependency.

Bereits gesetzte Umgebungsvariablen gewinnen immer über die Datei.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"


def parse_env(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        result[key.strip()] = value
    return result


def load_env(path: Path | str = ENV_FILE) -> None:
    path = Path(path)
    if not path.exists():
        return
    for key, value in parse_env(path.read_text(encoding="utf-8")).items():
        os.environ.setdefault(key, value)

PROFILE_FILE = ROOT / "config" / "profile.yaml"
PROFILE_EXAMPLE = ROOT / "config" / "profile.example.yaml"


def profile_path() -> Path:
    """config/profile.yaml, oder die mitgelieferte Example-Datei als Fallback."""
    return PROFILE_FILE if PROFILE_FILE.exists() else PROFILE_EXAMPLE
