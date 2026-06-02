from pathlib import Path


def app_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "2do-tools"


def backups_db_dir() -> Path:
    return app_support_dir() / "backups"


def backups_db_path() -> Path:
    return backups_db_dir() / "2do.db"
