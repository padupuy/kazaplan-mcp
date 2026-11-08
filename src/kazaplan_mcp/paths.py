"""Dossier de données du serveur : catalogue, sauvegardes .kzp, plans SVG.

KZ_DATA_DIR le fixe ; sinon ~/.cache/kazaplan-mcp ($XDG_CACHE_HOME, %LOCALAPPDATA% sous Windows).
"""

import os
from pathlib import Path


def data_dir() -> Path:
    if custom := os.environ.get("KZ_DATA_DIR"):
        return Path(custom).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "kazaplan-mcp"


DATA = data_dir()
CATALOG = DATA / "catalog"
BACKUPS = Path(os.environ.get("KZ_BACKUP_DIR") or DATA / "backups").expanduser()
SKETCHES = DATA / "sketches"
