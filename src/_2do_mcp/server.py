import json
import plistlib
import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .storage import backups_db_dir, backups_db_path

mcp = FastMCP("2Do")

# this is the sentinel value used to represent a null due date in 2Do
NULL_DUE_DATE_SENTINEL = 6406192800.0

TAG_DELIMITER = "_~|$$@$$|~_"

REQUIRED_BACKUP_COLUMNS = {
    "tasks": [
        "archived",
        "calendaruid",
        "completeddate",
        "creationstamp",
        "duedate",
        "iscompleted",
        "isdeleted",
        "notes",
        "primid",
        "tags",
        "title",
        "uid",
    ],
    "calendars": ["title", "uid"],
    "tags": ["isdeleted", "tag", "uid"],
}

BACKUPS_DB_DIR = backups_db_dir()
BACKUPS_DB_PATH = backups_db_path()
BACKUP_METADATA_PATH = BACKUPS_DB_DIR / "metadata.json"
AUTO_BACKUP_REFRESH_INTERVAL = timedelta(minutes=5)
_last_auto_refresh_check_at: datetime | None = None

GROUP_CONTAINER_ROOTS = [
    Path.home() / "Library" / "Group Containers",
]

GROUP_CONTAINER_IDS = [
    "EKT6323JY3.com.guidedways",
]

APP_BUNDLE_PATHS = [
    Path("/Applications/2Do.app"),
    Path.home() / "Applications" / "2Do.app",
]


class TaskList(BaseModel):
    id: str
    name: str


class Tag(BaseModel):
    id: str
    name: str


class Task(BaseModel):
    id: int
    uuid: str
    title: str
    notes: str | None = None
    date_created: datetime
    date_due: datetime | None = None
    date_completed: datetime | None = None
    completed: bool
    list: TaskList
    tags: list[Tag] = Field(default_factory=list)


@dataclass(frozen=True)
class TaskFilters:
    include_deleted: bool = False
    include_archived: bool = False
    completed: bool | None = None
    list_id: str | None = None
    tag_id: str | None = None
    due_from: datetime | None = None
    due_before: datetime | None = None
    limit: int = 1000


def _has_due_date_filter(filters: TaskFilters) -> bool:
    return filters.due_from is not None or filters.due_before is not None


def _to_2do_timestamp(value: datetime) -> float:
    return value.timestamp()


def _tag_filter_token(tag_id: str) -> str:
    return f"{TAG_DELIMITER}{tag_id}{TAG_DELIMITER}"


def _from_2do_timestamp(
    value: float | int | None, *, null_due_date: bool = False
) -> datetime | None:
    if value is None or value == 0:
        return None

    if null_due_date and value == NULL_DUE_DATE_SENTINEL:
        return None

    return datetime.fromtimestamp(value, UTC)


def _build_where_clause(filters: TaskFilters) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    if not filters.include_deleted:
        clauses.append("t.isdeleted = 0")

    if not filters.include_archived:
        clauses.append("t.archived = 0")

    if filters.completed is not None:
        clauses.append("t.iscompleted = ?")
        params.append(1 if filters.completed else 0)

    if filters.list_id is not None:
        clauses.append("t.calendaruid = ?")
        params.append(filters.list_id)

    if filters.tag_id is not None:
        clauses.append("instr(t.tags, ?) > 0")
        params.append(_tag_filter_token(filters.tag_id))

    if _has_due_date_filter(filters):
        clauses.append("t.duedate != ?")
        params.append(NULL_DUE_DATE_SENTINEL)

    if filters.due_from is not None:
        clauses.append("t.duedate >= ?")
        params.append(_to_2do_timestamp(filters.due_from))

    if filters.due_before is not None:
        clauses.append("t.duedate < ?")
        params.append(_to_2do_timestamp(filters.due_before))

    if not clauses:
        return "1 = 1", []

    return " and ".join(clauses), params


def _connect() -> sqlite3.Connection:
    ensure_backup_db_current()
    connection = sqlite3.connect(f"file:{BACKUPS_DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _get_tags_by_id(connection: sqlite3.Connection) -> dict[str, Tag]:
    rows = connection.execute(
        """
        select 
            uid as tag_id
            , tag as tag_name
        from tags
        where isdeleted = 0
          and uid is not null
          and uid != ''
        """
    ).fetchall()

    return {row["tag_id"]: Tag(id=row["tag_id"], name=row["tag_name"]) for row in rows}


def _parse_task_tags(raw_tags: str | None, tags_by_id: dict[str, Tag]) -> list[Tag]:
    if not raw_tags:
        return []

    parts = raw_tags.split(TAG_DELIMITER)
    tags: list[Tag] = []

    for id_index in range(4, len(parts), 7):
        tag = tags_by_id.get(parts[id_index])
        if tag is not None:
            tags.append(tag)

    return tags


def _get_tasks(filters: TaskFilters) -> list[Task]:
    where_clause, params = _build_where_clause(filters)
    limit = max(1, filters.limit)

    with _connect() as connection:
        tags_by_id = _get_tags_by_id(connection)

        rows = connection.execute(
            f"""
                select
                    t.primid as id
                    , t.uid as uuid
                    , t.title
                    , t.notes
                    , t.creationstamp as date_created
                    , t.duedate as date_due
                    , t.completeddate as date_completed
                    , t.iscompleted as completed
                    , t.tags
                    , c.uid as list_id
                    , c.title as list_name
                from tasks t
                join calendars c on c.uid = t.calendaruid
                where {where_clause}
                order by t.completeddate desc, t.duedate asc, t.creationstamp desc
                limit ?
            """,
            params + [limit],
        ).fetchall()

        return [
            Task(
                id=row["id"],
                uuid=row["uuid"],
                title=row["title"],
                notes=row["notes"] or None,
                date_created=datetime.fromtimestamp(row["date_created"], UTC),
                date_due=_from_2do_timestamp(row["date_due"], null_due_date=True),
                date_completed=_from_2do_timestamp(row["date_completed"]),
                completed=bool(row["completed"]),
                list=TaskList(id=row["list_id"], name=row["list_name"] or ""),
                tags=_parse_task_tags(row["tags"], tags_by_id),
            )
            for row in rows
        ]


def _count_tasks(filters: TaskFilters) -> int:
    where_clause, params = _build_where_clause(filters)

    with _connect() as connection:
        row = connection.execute(
            f"""
                select 
                    count(1) as n
                from tasks t
                where {where_clause}
            """,
            params,
        ).fetchone()

    return int(row["n"])


def ensure_backup_db_current(*, now: datetime | None = None) -> None:
    global _last_auto_refresh_check_at

    current_time = now or datetime.now(UTC)

    if not BACKUPS_DB_PATH.exists():
        refresh_backup()
        _last_auto_refresh_check_at = current_time
        return

    if (
        _last_auto_refresh_check_at is not None
        and current_time - _last_auto_refresh_check_at < AUTO_BACKUP_REFRESH_INTERVAL
    ):
        return

    refresh_backup()
    _last_auto_refresh_check_at = current_time


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _append_existing_candidate(
    candidates: list[Path], seen_paths: set[str], candidate: Path
) -> None:
    candidate_key = str(candidate)
    if candidate_key in seen_paths:
        return

    if _path_exists(candidate):
        candidates.append(candidate)
        seen_paths.add(candidate_key)


def _unique_strings(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen_values: set[str] = set()

    for value in values:
        if value in seen_values:
            continue

        unique_values.append(value)
        seen_values.add(value)

    return unique_values


def _discover_group_container_ids_from_app_bundles() -> list[str]:
    group_container_ids: list[str] = []

    for app_bundle_path in APP_BUNDLE_PATHS:
        info_plist_path = app_bundle_path / "Contents" / "Info.plist"
        if not _path_exists(info_plist_path):
            continue

        try:
            with info_plist_path.open("rb") as info_plist:
                app_info = plistlib.load(info_plist)
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue

        shared_defaults_key = app_info.get("BeehiveSharedDefaultsKey")
        if isinstance(shared_defaults_key, str) and shared_defaults_key:
            group_container_ids.append(shared_defaults_key)

    return _unique_strings(group_container_ids)


def _append_group_container_id_candidates(
    candidates: list[Path], seen_paths: set[str], group_container_ids: list[str]
) -> None:
    for root in GROUP_CONTAINER_ROOTS:
        for group_container_id in group_container_ids:
            _append_existing_candidate(
                candidates,
                seen_paths,
                root / group_container_id / "2do.db",
            )


def discover_candidate_dbs() -> list[Path]:
    seen_paths: set[str] = set()
    candidates: list[Path] = []

    group_container_ids = _unique_strings(
        GROUP_CONTAINER_IDS + _discover_group_container_ids_from_app_bundles()
    )

    _append_group_container_id_candidates(
        candidates,
        seen_paths,
        group_container_ids,
    )

    return candidates


def _copy_candidate_db_to_staging(source_db: Path) -> Path:
    token = secrets.token_hex(8)
    staging_dir = BACKUPS_DB_DIR / f".incoming-{token}"
    staging_dir.mkdir(parents=True, exist_ok=False)

    for source_file in source_db.parent.glob(f"{source_db.name}*"):
        shutil.copy2(source_file, staging_dir / source_file.name)

    return staging_dir


def _validate_backup_db(staging_dir: Path) -> bool:
    db_path = staging_dir / "2do.db"

    if not db_path.exists():
        return False

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check;").fetchone()
            if not integrity or integrity[0] != "ok":
                return False

            tables = {
                row[0]
                for row in connection.execute(
                    """
                        SELECT 
                            name
                        FROM sqlite_master
                        WHERE type = 'table'
                    """
                )
            }

            required_tables = set(REQUIRED_BACKUP_COLUMNS)
            if not required_tables.issubset(tables):
                return False

            for table, required_columns in REQUIRED_BACKUP_COLUMNS.items():
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table});")}
                if not set(required_columns).issubset(columns):
                    return False

            return True

    except sqlite3.Error:
        return False


def _promote_backup_db(staging_dir: Path) -> None:
    BACKUPS_DB_DIR.mkdir(parents=True, exist_ok=True)

    for existing_file in BACKUPS_DB_DIR.glob("2do.db*"):
        existing_file.unlink()

    for staged_file in staging_dir.glob("2do.db*"):
        shutil.move(str(staged_file), BACKUPS_DB_DIR / staged_file.name)

    staging_dir.rmdir()


def _read_backup_source_db_path() -> Path | None:
    try:
        raw_metadata = json.loads(BACKUP_METADATA_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    source_db_path = raw_metadata.get("source_db_path")
    if not isinstance(source_db_path, str) or not source_db_path:
        return None

    return Path(source_db_path)


def _write_backup_metadata(source_db: Path) -> None:
    BACKUP_METADATA_PATH.write_text(json.dumps({"source_db_path": str(source_db)}, indent=2) + "\n")


def _db_family_files(db_path: Path) -> dict[str, Path]:
    return {path.name: path for path in db_path.parent.glob(f"{db_path.name}*")}


def _tracked_source_db_is_unchanged() -> bool:
    source_db_path = _read_backup_source_db_path()
    if source_db_path is None or not BACKUPS_DB_PATH.exists():
        return False

    source_files = _db_family_files(source_db_path)
    backup_files = _db_family_files(BACKUPS_DB_PATH)

    if not source_files or set(source_files) != set(backup_files):
        return False

    try:
        return all(
            source_file.stat().st_mtime_ns <= backup_files[file_name].stat().st_mtime_ns
            for file_name, source_file in source_files.items()
        )
    except OSError:
        return False


def refresh_backup() -> bool:
    BACKUPS_DB_DIR.mkdir(parents=True, exist_ok=True)

    valid_staging_dirs: list[tuple[Path, Path]] = []

    try:
        if _tracked_source_db_is_unchanged():
            return False

        for candidate in discover_candidate_dbs():
            staging_dir = _copy_candidate_db_to_staging(candidate)

            if _validate_backup_db(staging_dir):
                valid_staging_dirs.append((candidate, staging_dir))
            else:
                shutil.rmtree(staging_dir, ignore_errors=True)

        if not valid_staging_dirs:
            raise RuntimeError(
                "No valid 2Do database found after copying candidates into backups/."
            )

        if len(valid_staging_dirs) > 1:
            sources = "\n".join(str(source) for source, _ in valid_staging_dirs)
            raise RuntimeError(f"Multiple valid 2Do databases found:\n{sources}")

        source_db, staging_dir = valid_staging_dirs[0]
        _promote_backup_db(staging_dir)
        _write_backup_metadata(source_db)
        return True

    finally:
        for incoming_dir in BACKUPS_DB_DIR.glob(".incoming-*"):
            shutil.rmtree(incoming_dir, ignore_errors=True)


@mcp.tool()
def get_completed_tasks() -> list[Task]:
    """Get the list of completed tasks in 2Do"""
    return _get_tasks(TaskFilters(completed=True))


@mcp.tool()
def count_completed_tasks() -> int:
    """Count the number of completed tasks in 2Do"""
    return _count_tasks(TaskFilters(completed=True))


@mcp.tool()
def get_open_tasks() -> list[Task]:
    """Get the list of open tasks in 2Do"""
    return _get_tasks(TaskFilters(completed=False))


@mcp.tool()
def count_open_tasks() -> int:
    """Count the number of open tasks in 2Do"""
    return _count_tasks(TaskFilters(completed=False))


@mcp.tool()
def refresh_backup_db() -> None:
    refresh_backup()


if __name__ == "__main__":
    ensure_backup_db_current()
    mcp.run()
