import asyncio
import json
import plistlib
import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from fastmcp import Context, FastMCP
from fastmcp.server.elicitation import AcceptedElicitation
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .storage import backups_db_dir, backups_db_path
from .task_creation import (
    ConfirmationResult,
    ConfirmationStatus,
    RepeatPreset,
    TaskCompletionResult,
    TaskCompletionStatus,
    TaskCreationResult,
    TaskCreationStatus,
    TaskDraft,
    complete_task_direct,
    confirm_action_native,
    create_task_direct,
    task_preview,
)
from .url_schemes import add_task_url, open_url, search_url, show_list_url, show_task_url

MCP_INSTRUCTIONS = (
    "2Do Tools reads from a local, read-only backup of the 2Do macOS task database. "
    "Use list_tasks for filtered lookup and the list_tasks_* shortcuts for common date groups. "
    "Use exact local dates for relative date requests. Task and list results include twodo:// "
    "URLs. open_task/open_list/open_search only open views on the Mac running the server; use "
    "them when the user asks to open something. open_task_quick_entry opens a pre-filled editor "
    "that the user must save in 2Do. create_task creates directly only after MCP elicitation or "
    "native confirmation on the host Mac. complete_task completes exactly one existing task after "
    "the same confirmation. Run refresh_backup_db if results look stale."
)

mcp = FastMCP("2Do", instructions=MCP_INSTRUCTIONS)

# this is the sentinel value used to represent a null due date in 2Do
NULL_DUE_DATE_SENTINEL = 6406192800.0

TAG_DELIMITER = "_~|$$@$$|~_"

REPEAT_TYPE_UNITS = {
    256: ("day", "days"),
    257: ("week", "weeks"),
    258: ("month", "months"),
    259: ("year", "years"),
}

REPEAT_VALUE_PRESET_SCHEDULES = {
    1: "every day",
    2: "every week",
    3: "every 2 weeks",
    4: "every month",
}

RECURRENCE_REPEAT_FROM = {
    1: "due_date",
    2: "completion_date",
}

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
        "recurrence",
        "recurrenceenddate",
        "recurrenceendrepeats",
        "recurrenceendtype",
        "repeattype",
        "repeatvalue",
        "tags",
        "title",
        "uid",
    ],
    "calendars": [
        "isarchived",
        "isdeleted",
        "isinboxcal",
        "parentuid",
        "title",
        "uid",
    ],
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
    url: str


class Tag(BaseModel):
    id: str
    name: str


class TaskRecurrenceEnd(BaseModel):
    kind: str
    count: int | None = None
    date: datetime | None = None


class TaskRecurrence(BaseModel):
    schedule: str
    repeat_from: str | None = None
    end: TaskRecurrenceEnd | None = None
    raw_recurrence: int
    raw_repeatvalue: int
    raw_repeattype: int


class Task(BaseModel):
    id: int
    uuid: str
    url: str
    title: str
    notes: str | None = None
    date_created: datetime
    date_due: datetime | None = None
    date_completed: datetime | None = None
    completed: bool
    recurring: bool = False
    recurrence: TaskRecurrence | None = None
    list: TaskList
    tags: list[Tag] = Field(default_factory=list)


@dataclass(frozen=True)
class TaskFilters:
    include_deleted: bool = False
    include_archived: bool = False
    completed: bool | None = None
    task_uid: str | None = None
    list_id: str | None = None
    list_name: str | None = None
    tag_id: str | None = None
    tag_name: str | None = None
    due_from: datetime | None = None
    due_before: datetime | None = None
    has_due_date: bool = False
    completed_from: datetime | None = None
    completed_before: datetime | None = None
    recurring: bool | None = None
    query: str | None = None
    limit: int = 1000


class OpenedUrl(BaseModel):
    url: str
    opened: bool


def _has_due_date_filter(filters: TaskFilters) -> bool:
    return filters.has_due_date or filters.due_from is not None or filters.due_before is not None


def _has_completed_date_filter(filters: TaskFilters) -> bool:
    return filters.completed_from is not None or filters.completed_before is not None


def _local_today() -> date:
    return datetime.now().astimezone().date()


def _local_start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min).astimezone()


def _today_window() -> tuple[datetime, datetime]:
    today = _local_today()
    return _local_start_of_day(today), _local_start_of_day(today + timedelta(days=1))


def _calendar_week_window() -> tuple[datetime, datetime]:
    today = _local_today()
    week_start = today - timedelta(days=today.weekday())
    return _local_start_of_day(week_start), _local_start_of_day(week_start + timedelta(days=7))


def _overdue_window() -> tuple[None, datetime]:
    return None, _local_start_of_day(_local_today())


def _date_range_bounds(
    from_date: date | None,
    before_date: date | None,
) -> tuple[datetime | None, datetime | None]:
    return (
        _local_start_of_day(from_date) if from_date is not None else None,
        _local_start_of_day(before_date) if before_date is not None else None,
    )


def _to_2do_timestamp(value: datetime) -> float:
    return value.timestamp()


def _tag_filter_token(tag_id: str) -> str:
    return f"{TAG_DELIMITER}{tag_id}{TAG_DELIMITER}"


def _query_pattern(value: str) -> str:
    return f"%{value}%"


def _from_2do_timestamp(
    value: float | int | None, *, null_due_date: bool = False
) -> datetime | None:
    if value is None or value == 0:
        return None

    if null_due_date and value == NULL_DUE_DATE_SENTINEL:
        return None

    return datetime.fromtimestamp(value, UTC)


def _int_or_zero(value: object) -> int:
    if value is None:
        return 0

    return int(value)


def _format_interval_schedule(repeat_type: int, repeat_value: int) -> str | None:
    units = REPEAT_TYPE_UNITS.get(repeat_type)
    if units is None:
        return None

    interval = repeat_value if repeat_value > 0 else 1
    unit = units[0] if interval == 1 else units[1]

    if interval == 1:
        return f"every {unit}"

    return f"every {interval} {unit}"


def _format_repeat_schedule(repeat_type: int, repeat_value: int) -> str:
    interval_schedule = _format_interval_schedule(repeat_type, repeat_value)
    if interval_schedule is not None:
        return interval_schedule

    if repeat_type == 0 and repeat_value in REPEAT_VALUE_PRESET_SCHEDULES:
        return REPEAT_VALUE_PRESET_SCHEDULES[repeat_value]

    if 0 < repeat_type < 256:
        return f"weekly on selected weekdays (raw mask {repeat_type})"

    return f"custom repeat pattern (repeat type {repeat_type}, repeat value {repeat_value})"


def _parse_task_recurrence_end(
    recurrence_end_type: int,
    recurrence_end_repeats: int,
    recurrence_end_date: float | int | None,
) -> TaskRecurrenceEnd | None:
    if recurrence_end_type == 0:
        return None

    end_date = _from_2do_timestamp(recurrence_end_date)

    if recurrence_end_repeats > 0:
        return TaskRecurrenceEnd(
            kind="after_occurrences",
            count=recurrence_end_repeats,
            date=end_date,
        )

    if end_date is not None:
        return TaskRecurrenceEnd(kind="on_date", date=end_date)

    return TaskRecurrenceEnd(kind=f"unknown:{recurrence_end_type}")


def _parse_task_recurrence(row: sqlite3.Row) -> TaskRecurrence | None:
    repeat_type = _int_or_zero(row["repeattype"])
    repeat_value = _int_or_zero(row["repeatvalue"])

    if repeat_type == 0 and repeat_value == 0:
        return None

    raw_recurrence = _int_or_zero(row["recurrence"])

    return TaskRecurrence(
        schedule=_format_repeat_schedule(repeat_type, repeat_value),
        repeat_from=RECURRENCE_REPEAT_FROM.get(raw_recurrence),
        end=_parse_task_recurrence_end(
            _int_or_zero(row["recurrenceendtype"]),
            _int_or_zero(row["recurrenceendrepeats"]),
            row["recurrenceenddate"],
        ),
        raw_recurrence=raw_recurrence,
        raw_repeatvalue=repeat_value,
        raw_repeattype=repeat_type,
    )


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

    if filters.task_uid is not None:
        clauses.append("t.uid = ?")
        params.append(filters.task_uid)

    if filters.list_id is not None:
        clauses.append("t.calendaruid = ?")
        params.append(filters.list_id)
    elif filters.list_name is not None:
        clauses.append("lower(coalesce(c.title, '')) = lower(?)")
        params.append(filters.list_name)

    if filters.tag_id is not None:
        clauses.append("instr(t.tags, ?) > 0")
        params.append(_tag_filter_token(filters.tag_id))
    elif filters.tag_name is not None:
        clauses.append(
            """
            exists (
                select 1
                from tags tag
                where tag.isdeleted = 0
                  and lower(coalesce(tag.tag, '')) = lower(?)
                  and instr(t.tags, ? || tag.uid || ?) > 0
            )
            """
        )
        params.extend([filters.tag_name, TAG_DELIMITER, TAG_DELIMITER])

    if _has_due_date_filter(filters):
        clauses.append("t.duedate is not null")
        clauses.append("t.duedate != 0")
        clauses.append("t.duedate != ?")
        params.append(NULL_DUE_DATE_SENTINEL)

    if filters.due_from is not None:
        clauses.append("t.duedate >= ?")
        params.append(_to_2do_timestamp(filters.due_from))

    if filters.due_before is not None:
        clauses.append("t.duedate < ?")
        params.append(_to_2do_timestamp(filters.due_before))

    if filters.recurring is not None:
        recurrence_test = "(coalesce(t.repeattype, 0) != 0 or coalesce(t.repeatvalue, 0) != 0)"
        clauses.append(recurrence_test if filters.recurring else f"not {recurrence_test}")

    if _has_completed_date_filter(filters):
        clauses.append("t.completeddate is not null")
        clauses.append("t.completeddate != 0")

    if filters.completed_from is not None:
        clauses.append("t.completeddate >= ?")
        params.append(_to_2do_timestamp(filters.completed_from))

    if filters.completed_before is not None:
        clauses.append("t.completeddate < ?")
        params.append(_to_2do_timestamp(filters.completed_before))

    query = filters.query.strip() if filters.query is not None else ""
    if query:
        pattern = _query_pattern(query)
        clauses.append(
            """
            (
                lower(coalesce(t.title, '')) like lower(?)
                or lower(coalesce(t.notes, '')) like lower(?)
                or lower(coalesce(c.title, '')) like lower(?)
                or exists (
                    select 1
                    from tags tag
                    where tag.isdeleted = 0
                      and lower(coalesce(tag.tag, '')) like lower(?)
                      and instr(t.tags, ? || tag.uid || ?) > 0
                )
            )
            """
        )
        params.extend(
            [
                pattern,
                pattern,
                pattern,
                pattern,
                TAG_DELIMITER,
                TAG_DELIMITER,
            ]
        )

    if not clauses:
        return "1 = 1", []

    return " and ".join(clauses), params


def _connect() -> sqlite3.Connection:
    ensure_backup_db_current()
    connection = sqlite3.connect(f"file:{BACKUPS_DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _get_lists() -> list[TaskList]:
    with _connect() as connection:
        rows = connection.execute(
            """
            select
                uid as list_id
                , title as list_name
            from calendars
            where uid is not null
              and uid != ''
              and coalesce(isdeleted, 0) = 0
              and coalesce(isarchived, 0) = 0
              and parentuid in ('2DoCalGroupLists', '2DoCalGroupInbox')
            order by lower(coalesce(title, '')), uid
            """
        ).fetchall()

    return [
        TaskList(
            id=row["list_id"],
            name=row["list_name"] or "",
            url=show_list_url(row["list_name"] or ""),
        )
        for row in rows
    ]


def _get_inbox_list() -> TaskList:
    with _connect() as connection:
        row = connection.execute(
            """
            select
                uid as list_id
                , title as list_name
            from calendars
            where coalesce(isinboxcal, 0) = 1
              and coalesce(isdeleted, 0) = 0
            order by uid
            limit 1
            """
        ).fetchone()

    if row is None:
        raise ValueError("2Do inbox list not found")

    list_name = row["list_name"] or ""
    return TaskList(
        id=row["list_id"],
        name=list_name,
        url=show_list_url(list_name),
    )


def _find_list_name(name: str) -> str | None:
    requested_name = name.casefold()

    for task_list in _get_lists():
        if task_list.name.casefold() == requested_name:
            return task_list.name

    return None


def _resolve_list_name(name: str) -> str:
    try:
        return _find_list_name(name) or name
    except (OSError, RuntimeError, sqlite3.Error):
        return name


def _require_list_name(name: str | None) -> str:
    if name is None:
        return _get_inbox_list().name

    resolved_name = _find_list_name(name)
    if resolved_name is None:
        raise ValueError(f"2Do list not found: {name}")
    return resolved_name


def _task_draft(
    title: str,
    notes: str | None,
    list_name: str | None,
    due_date: date | None,
    tags: list[str] | None,
    repeat: RepeatPreset | None,
) -> TaskDraft:
    return TaskDraft(
        title=title,
        notes=notes,
        list_name=_require_list_name(list_name),
        due_date=due_date,
        tags=tags,
        repeat=repeat,
    )


def _get_tags() -> list[Tag]:
    with _connect() as connection:
        rows = connection.execute(
            """
            select
                uid as tag_id
                , tag as tag_name
            from tags
            where isdeleted = 0
              and uid is not null
              and uid != ''
            order by lower(coalesce(tag, '')), uid
            """
        ).fetchall()

    return [Tag(id=row["tag_id"], name=row["tag_name"] or "") for row in rows]


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


def _task_from_row(row: sqlite3.Row, tags_by_id: dict[str, Tag]) -> Task:
    recurrence = _parse_task_recurrence(row)
    list_name = row["list_name"] or ""

    return Task(
        id=row["id"],
        uuid=row["uuid"],
        url=show_task_url(row["uuid"]),
        title=row["title"],
        notes=row["notes"] or None,
        date_created=datetime.fromtimestamp(row["date_created"], UTC),
        date_due=_from_2do_timestamp(row["date_due"], null_due_date=True),
        date_completed=_from_2do_timestamp(row["date_completed"]),
        completed=bool(row["completed"]),
        recurring=recurrence is not None,
        recurrence=recurrence,
        list=TaskList(
            id=row["list_id"],
            name=list_name,
            url=show_list_url(list_name),
        ),
        tags=_parse_task_tags(row["tags"], tags_by_id),
    )


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
                    , t.recurrence
                    , t.repeatvalue
                    , t.repeattype
                    , t.recurrenceendtype
                    , t.recurrenceendrepeats
                    , t.recurrenceenddate
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

        return [_task_from_row(row, tags_by_id) for row in rows]


def _get_task(uid: str) -> Task | None:
    tasks = _get_tasks(
        TaskFilters(
            include_archived=True,
            task_uid=uid,
            limit=1,
        )
    )
    return tasks[0] if tasks else None


def _require_open_task(uid: str) -> Task:
    task = _get_task(uid)
    if task is None:
        raise ValueError(f"2Do task not found: {uid}")
    if task.completed:
        raise ValueError(f"Task is already complete: {task.title}")
    return task


def task_completion_preview(task: Task) -> str:
    return f"Title: {task.title}\nList: {task.list.name}\nUID: {task.uuid}"


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
def list_lists() -> list[TaskList]:
    """List 2Do lists."""
    return _get_lists()


@mcp.tool()
def list_tags() -> list[Tag]:
    """List non-deleted 2Do tags."""
    return _get_tags()


@mcp.tool()
def list_tasks(
    completed: bool | None = None,
    list_id: str | None = None,
    list_name: str | None = None,
    tag_id: str | None = None,
    tag_name: str | None = None,
    due_from: date | None = None,
    due_before: date | None = None,
    has_due_date: bool = False,
    completed_from: date | None = None,
    completed_before: date | None = None,
    query: str | None = None,
    limit: int = 1000,
) -> list[Task]:
    """Search and filter 2Do tasks."""
    due_from_bound, due_before_bound = _date_range_bounds(due_from, due_before)
    completed_from_bound, completed_before_bound = _date_range_bounds(
        completed_from,
        completed_before,
    )

    return _get_tasks(
        TaskFilters(
            completed=completed,
            list_id=list_id,
            list_name=list_name,
            tag_id=tag_id,
            tag_name=tag_name,
            due_from=due_from_bound,
            due_before=due_before_bound,
            has_due_date=has_due_date,
            completed_from=completed_from_bound,
            completed_before=completed_before_bound,
            query=query,
            limit=limit,
        )
    )


@mcp.tool()
def list_tasks_overdue(limit: int = 1000) -> list[Task]:
    """List open tasks due before today."""
    _due_from, due_before = _overdue_window()
    return _get_tasks(
        TaskFilters(
            completed=False,
            due_before=due_before,
            limit=limit,
        )
    )


@mcp.tool()
def list_tasks_inbox(limit: int = 1000) -> list[Task]:
    """List open tasks in the Inbox list."""
    return _get_tasks(TaskFilters(completed=False, list_name="Inbox", limit=limit))


@mcp.tool()
def list_tasks_due_today(limit: int = 1000) -> list[Task]:
    """List open tasks due today."""
    due_from, due_before = _today_window()
    return _get_tasks(
        TaskFilters(
            completed=False,
            due_from=due_from,
            due_before=due_before,
            limit=limit,
        )
    )


@mcp.tool()
def list_tasks_due_this_week(limit: int = 1000) -> list[Task]:
    """List open tasks due during the current calendar week."""
    due_from, due_before = _calendar_week_window()
    return _get_tasks(
        TaskFilters(
            completed=False,
            due_from=due_from,
            due_before=due_before,
            limit=limit,
        )
    )


@mcp.tool()
def list_tasks_completed_today(limit: int = 1000) -> list[Task]:
    """List tasks completed today."""
    completed_from, completed_before = _today_window()
    return _get_tasks(
        TaskFilters(
            completed=True,
            completed_from=completed_from,
            completed_before=completed_before,
            limit=limit,
        )
    )


@mcp.tool()
def list_tasks_completed_this_week(limit: int = 1000) -> list[Task]:
    """List tasks completed during the current calendar week."""
    completed_from, completed_before = _calendar_week_window()
    return _get_tasks(
        TaskFilters(
            completed=True,
            completed_from=completed_from,
            completed_before=completed_before,
            limit=limit,
        )
    )


@mcp.tool()
def open_task(uid: str) -> OpenedUrl:
    """Open a task in 2Do by UID."""
    url = show_task_url(uid)
    open_url(url)
    return OpenedUrl(url=url, opened=True)


@mcp.tool()
def open_list(name: str) -> OpenedUrl:
    """Open a 2Do list by name."""
    url = show_list_url(_resolve_list_name(name))
    open_url(url)
    return OpenedUrl(url=url, opened=True)


@mcp.tool()
def open_search(text: str) -> OpenedUrl:
    """Open a 2Do search."""
    url = search_url(text)
    open_url(url)
    return OpenedUrl(url=url, opened=True)


@mcp.tool()
def open_task_quick_entry(
    title: str,
    notes: str | None = None,
    list_name: str | None = None,
    due_date: date | None = None,
    tags: list[str] | None = None,
    repeat: RepeatPreset | None = None,
) -> OpenedUrl:
    """Open a pre-filled Quick Entry editor in 2Do without saving the task."""
    draft = _task_draft(title, notes, list_name, due_date, tags, repeat)
    url = add_task_url(
        title=draft.title,
        notes=draft.notes,
        list_name=draft.list_name,
        due_date=draft.due_date,
        tags=draft.tags,
        repeat=draft.repeat.url_value if draft.repeat is not None else None,
        use_quick_entry=True,
    )
    open_url(url)
    return OpenedUrl(url=url, opened=True)


def _supports_form_elicitation(ctx: Context) -> bool:
    client_params = ctx.session.client_params
    if client_params is None:
        return False

    elicitation = client_params.capabilities.elicitation
    return elicitation is not None and elicitation.form is not None


async def _confirm(
    ctx: Context,
    preview: str,
    *,
    response_title: str,
    action: str,
    operation: str,
) -> ConfirmationResult:
    if _supports_form_elicitation(ctx):
        try:
            response = await ctx.elicit(
                preview,
                bool,
                response_title=response_title,
            )
        except Exception as exc:
            return ConfirmationResult(
                status=ConfirmationStatus.FAILED,
                message=f"Could not confirm task {operation}: {exc}",
            )

        if isinstance(response, AcceptedElicitation) and response.data is True:
            return ConfirmationResult(
                status=ConfirmationStatus.CONFIRMED,
                message=f"Task {operation} confirmed.",
            )

        return ConfirmationResult(
            status=ConfirmationStatus.CANCELLED,
            message=f"Task {operation} cancelled.",
        )

    return await asyncio.to_thread(
        confirm_action_native,
        preview,
        action=action,
        operation=operation,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
async def create_task(
    ctx: Context,
    title: str,
    notes: str | None = None,
    list_name: str | None = None,
    due_date: date | None = None,
    tags: list[str] | None = None,
    repeat: RepeatPreset | None = None,
) -> TaskCreationResult:
    """Create a 2Do task after explicit user confirmation."""
    draft = await asyncio.to_thread(
        _task_draft,
        title=title,
        notes=notes,
        list_name=list_name,
        due_date=due_date,
        tags=tags,
        repeat=repeat,
    )
    confirmation = await _confirm(
        ctx,
        task_preview(draft),
        response_title="Create this task?",
        action="Create",
        operation="creation",
    )
    if confirmation.status is not ConfirmationStatus.CONFIRMED:
        return TaskCreationResult(
            status=(
                TaskCreationStatus.CANCELLED
                if confirmation.status is ConfirmationStatus.CANCELLED
                else TaskCreationStatus.FAILED
            ),
            message=confirmation.message,
        )

    return await asyncio.to_thread(create_task_direct, draft)


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
async def complete_task(ctx: Context, uid: str) -> TaskCompletionResult:
    """Complete one existing 2Do task after explicit user confirmation."""
    task = await asyncio.to_thread(_require_open_task, uid)
    preview = task_completion_preview(task)
    confirmation = await _confirm(
        ctx,
        preview,
        response_title="Complete this task?",
        action="Complete",
        operation="completion",
    )
    if confirmation.status is not ConfirmationStatus.CONFIRMED:
        return TaskCompletionResult(
            status=(
                TaskCompletionStatus.CANCELLED
                if confirmation.status is ConfirmationStatus.CANCELLED
                else TaskCompletionStatus.FAILED
            ),
            uid=task.uuid,
            task_url=task.url,
            message=confirmation.message,
        )

    return await asyncio.to_thread(complete_task_direct, task.uuid)


@mcp.tool()
def refresh_backup_db() -> None:
    refresh_backup()


if __name__ == "__main__":
    ensure_backup_db_current()
    mcp.run()
