import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import _2do_tools.server as server

CREATED_AT = datetime(2024, 1, 2, 12, 0, tzinfo=UTC).timestamp()
DUE_AT = datetime(2024, 1, 4, 9, 0, tzinfo=UTC).timestamp()
COMPLETED_AT = datetime(2024, 1, 5, 15, 0, tzinfo=UTC).timestamp()

TASK_INSERT_SQL = """
insert into tasks (
    primid, uid, title, notes, creationstamp, duedate,
    completeddate, iscompleted, tags, calendaruid, isdeleted, archived,
    recurrence, repeatvalue, repeattype, recurrenceendtype, recurrenceendrepeats,
    recurrenceenddate
)
values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _raw_tags(*tag_ids: str) -> str:
    parts: list[str] = []
    for tag_id in tag_ids:
        parts.extend(["", "", "", "", tag_id, "", ""])
    return server.TAG_DELIMITER.join(parts)


def _create_query_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table calendars (
            uid text,
            title text
        );

        create table tags (
            uid text,
            tag text,
            isdeleted integer
        );

        create table tasks (
            primid integer,
            uid text,
            title text,
            notes text,
            creationstamp real,
            duedate real,
            completeddate real,
            iscompleted integer,
            tags text,
            calendaruid text,
            isdeleted integer,
            archived integer,
            recurrence integer,
            repeatvalue integer,
            repeattype integer,
            recurrenceendtype integer,
            recurrenceendrepeats integer,
            recurrenceenddate real
        );
        """
    )


def _insert_task(
    connection: sqlite3.Connection,
    *,
    primid: int,
    uid: str,
    title: str,
    notes: str | None = None,
    creationstamp: float = CREATED_AT,
    duedate: float = 0,
    completeddate: float = 0,
    iscompleted: int = 0,
    tags: str | None = None,
    calendaruid: str = "list-inbox",
    isdeleted: int = 0,
    archived: int = 0,
    recurrence: int = 0,
    repeatvalue: int = 0,
    repeattype: int = 0,
    recurrenceendtype: int = 0,
    recurrenceendrepeats: int = 0,
    recurrenceenddate: float = 0,
) -> None:
    connection.execute(
        TASK_INSERT_SQL,
        (
            primid,
            uid,
            title,
            notes,
            creationstamp,
            duedate,
            completeddate,
            iscompleted,
            tags,
            calendaruid,
            isdeleted,
            archived,
            recurrence,
            repeatvalue,
            repeattype,
            recurrenceendtype,
            recurrenceendrepeats,
            recurrenceenddate,
        ),
    )


def _create_required_schema_backup(
    staging_dir: Path,
    *,
    omitted_table: str | None = None,
    omitted_column: tuple[str, str] | None = None,
) -> None:
    staging_dir.mkdir()
    db_path = staging_dir / "2do.db"

    with sqlite3.connect(db_path) as connection:
        for table, required_columns in server.REQUIRED_BACKUP_COLUMNS.items():
            if table == omitted_table:
                continue

            columns = [column for column in required_columns if omitted_column != (table, column)]
            column_definitions = ", ".join(f"{column} text" for column in columns)
            connection.execute(f"create table {table} ({column_definitions})")


@pytest.fixture
def fake_2do_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "2do.db"

    with sqlite3.connect(db_path) as connection:
        _create_query_schema(connection)

        connection.executemany(
            "insert into calendars (uid, title) values (?, ?)",
            [
                ("list-inbox", "Inbox"),
                ("list-projects", "Projects"),
            ],
        )
        connection.executemany(
            "insert into tags (uid, tag, isdeleted) values (?, ?, ?)",
            [
                ("tag-work", "Work", 0),
                ("tag-home", "Home", 0),
                ("tag-deleted", "Deleted tag", 1),
            ],
        )
        _insert_task(
            connection,
            primid=1,
            uid="task-active",
            title="Active task",
            notes="Remember milk",
            duedate=server.NULL_DUE_DATE_SENTINEL,
            tags=_raw_tags("tag-work", "tag-deleted"),
        )
        _insert_task(
            connection,
            primid=2,
            uid="task-deleted",
            title="Deleted task",
            isdeleted=1,
        )
        _insert_task(
            connection,
            primid=3,
            uid="task-archived",
            title="Archived task",
            archived=1,
        )

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(server, "_connect", connect)
    return db_path


@pytest.fixture
def rich_2do_db(fake_2do_db: Path) -> Path:
    with sqlite3.connect(fake_2do_db) as connection:
        _insert_task(
            connection,
            primid=4,
            uid="task-completed",
            title="Completed task",
            completeddate=COMPLETED_AT,
            iscompleted=1,
        )
        _insert_task(
            connection,
            primid=5,
            uid="task-project",
            title="Project task",
            calendaruid="list-projects",
        )
        _insert_task(
            connection,
            primid=6,
            uid="task-home",
            title="Home tagged task",
            tags=_raw_tags("tag-home"),
        )
        _insert_task(
            connection,
            primid=7,
            uid="task-query",
            title="Query task",
            notes="Contains specialphrase",
        )

    return fake_2do_db


def test_null_due_date_sentinel_is_treated_as_missing_due_date() -> None:
    assert server._from_2do_timestamp(server.NULL_DUE_DATE_SENTINEL, null_due_date=True) is None


def test_null_due_date_sentinel_is_timestamp_outside_due_date_context() -> None:
    assert server._from_2do_timestamp(server.NULL_DUE_DATE_SENTINEL) == datetime.fromtimestamp(
        server.NULL_DUE_DATE_SENTINEL,
        UTC,
    )


def test_get_tasks_maps_active_tasks_from_sqlite_backup(fake_2do_db: Path) -> None:
    tasks = server._get_tasks(server.TaskFilters())

    assert [task.title for task in tasks] == ["Active task"]

    task = tasks[0]
    assert task.id == 1
    assert task.uuid == "task-active"
    assert task.notes == "Remember milk"
    assert task.date_created == datetime.fromtimestamp(CREATED_AT, UTC)
    assert task.date_due is None
    assert task.date_completed is None
    assert task.completed is False
    assert task.recurring is False
    assert task.recurrence is None
    assert task.url == "twodo://x-callback-url/showtask?uid=task-active"
    assert task.list.id == "list-inbox"
    assert task.list.name == "Inbox"
    assert task.list.url == "twodo://x-callback-url/showlist?name=Inbox"
    assert [(tag.id, tag.name) for tag in task.tags] == [("tag-work", "Work")]


def test_list_lists_includes_showlist_urls(fake_2do_db: Path) -> None:
    lists = server._get_lists()

    assert [(task_list.name, task_list.url) for task_list in lists] == [
        ("Inbox", "twodo://x-callback-url/showlist?name=Inbox"),
        ("Projects", "twodo://x-callback-url/showlist?name=Projects"),
    ]


def test_get_tasks_maps_recurring_task_schedule(fake_2do_db: Path) -> None:
    end_at = datetime(2024, 2, 1, 0, 0, tzinfo=UTC).timestamp()
    with sqlite3.connect(fake_2do_db) as connection:
        _insert_task(
            connection,
            primid=4,
            uid="task-recurring",
            title="Recurring task",
            recurrence=2,
            repeatvalue=3,
            repeattype=258,
            recurrenceendtype=1,
            recurrenceenddate=end_at,
        )

    tasks = server._get_tasks(server.TaskFilters(query="Recurring task"))

    task = tasks[0]
    assert task.recurring is True
    assert task.recurrence is not None
    assert task.recurrence.schedule == "every 3 months"
    assert task.recurrence.repeat_from == "completion_date"
    assert task.recurrence.end is not None
    assert task.recurrence.end.kind == "on_date"
    assert task.recurrence.end.date == datetime.fromtimestamp(end_at, UTC)
    assert task.recurrence.raw_recurrence == 2
    assert task.recurrence.raw_repeatvalue == 3
    assert task.recurrence.raw_repeattype == 258


def test_due_date_filters_exclude_null_due_date_sentinel(fake_2do_db: Path) -> None:
    with sqlite3.connect(fake_2do_db) as connection:
        _insert_task(
            connection,
            primid=4,
            uid="task-dated",
            title="Dated task",
            duedate=DUE_AT,
        )

    tasks = server._get_tasks(server.TaskFilters(due_from=datetime(2024, 1, 1, tzinfo=UTC)))

    assert [task.title for task in tasks] == ["Dated task"]


@pytest.mark.parametrize(
    ("filters", "expected_titles"),
    [
        (server.TaskFilters(completed=True), ["Completed task"]),
        (server.TaskFilters(list_name="Projects"), ["Project task"]),
        (server.TaskFilters(tag_name="Home"), ["Home tagged task"]),
        (server.TaskFilters(query="specialphrase"), ["Query task"]),
    ],
)
def test_get_tasks_applies_filters(
    rich_2do_db: Path,
    filters: server.TaskFilters,
    expected_titles: list[str],
) -> None:
    tasks = server._get_tasks(filters)

    assert [task.title for task in tasks] == expected_titles


def test_validate_backup_db_accepts_minimal_required_schema(tmp_path: Path) -> None:
    staging_dir = tmp_path / "valid"
    _create_required_schema_backup(staging_dir)

    assert server._validate_backup_db(staging_dir) is True


@pytest.mark.parametrize(
    ("omitted_table", "omitted_column"),
    [
        ("tasks", None),
        (None, ("tasks", "uid")),
    ],
)
def test_validate_backup_db_rejects_missing_required_schema(
    tmp_path: Path,
    omitted_table: str | None,
    omitted_column: tuple[str, str] | None,
) -> None:
    staging_dir = tmp_path / "invalid"
    _create_required_schema_backup(
        staging_dir,
        omitted_table=omitted_table,
        omitted_column=omitted_column,
    )

    assert server._validate_backup_db(staging_dir) is False


def test_refresh_backup_promotes_single_valid_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "source"
    backups_dir = tmp_path / "backups"
    backup_db_path = backups_dir / "2do.db"
    metadata_path = backups_dir / "metadata.json"
    _create_required_schema_backup(source_dir)
    source_db_path = source_dir / "2do.db"

    backups_dir.mkdir()
    backup_db_path.write_text("old backup")

    monkeypatch.setattr(server, "BACKUPS_DB_DIR", backups_dir)
    monkeypatch.setattr(server, "BACKUPS_DB_PATH", backup_db_path)
    monkeypatch.setattr(server, "BACKUP_METADATA_PATH", metadata_path)
    monkeypatch.setattr(server, "discover_candidate_dbs", lambda: [source_db_path])

    assert server.refresh_backup() is True
    assert server._validate_backup_db(backups_dir) is True
    assert json.loads(metadata_path.read_text()) == {
        "source_db_path": str(source_db_path),
    }
    assert list(backups_dir.glob(".incoming-*")) == []


def test_open_task_opens_showtask_url(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(server, "open_url", opened_urls.append)

    result = server.open_task("task-active")

    assert opened_urls == ["twodo://x-callback-url/showtask?uid=task-active"]
    assert result.url == "twodo://x-callback-url/showtask?uid=task-active"
    assert result.opened is True


def test_open_list_opens_showlist_url(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(server, "open_url", opened_urls.append)

    result = server.open_list("Work & Home")

    assert opened_urls == ["twodo://x-callback-url/showlist?name=Work%20%26%20Home"]
    assert result.url == "twodo://x-callback-url/showlist?name=Work%20%26%20Home"
    assert result.opened is True


def test_open_search_opens_search_url(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(server, "open_url", opened_urls.append)

    result = server.open_search("invoice, admin")

    assert opened_urls == ["twodo://x-callback-url/search?text=invoice%2C%20admin"]
    assert result.url == "twodo://x-callback-url/search?text=invoice%2C%20admin"
    assert result.opened is True
