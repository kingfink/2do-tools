import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("2Do")

# this is the sentinel value used to represent a null due date in 2Do
NULL_DUE_DATE_SENTINEL = 6406192800.0

TAG_DELIMITER = "_~|$$@$$|~_"

BACKUPS_DB_PATH = Path(__file__).parent / "backups" / "2do.db"


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


def _from_2do_timestamp(
    value: float | int | None, *, null_due_date: bool = False
) -> datetime | None:
    if value is None or value == 0:
        return None

    if null_due_date and value == NULL_DUE_DATE_SENTINEL:
        return None

    return datetime.fromtimestamp(value, timezone.utc)


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
        clauses.append("t.tags LIKE ?")
        params.append(f"%{filters.tag_id}%")

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
                date_created=datetime.fromtimestamp(row["date_created"], timezone.utc),
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


if __name__ == "__main__":
    mcp.run()
