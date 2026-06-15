import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)

import _2do_tools.server as server
from _2do_tools.task_creation import (
    ConfirmationResult,
    ConfirmationStatus,
    TaskCompletionResult,
    TaskCompletionStatus,
    TaskCreationResult,
    TaskCreationStatus,
)

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
            title text,
            isdeleted integer,
            isarchived integer
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
            "insert into calendars (uid, title, isdeleted, isarchived) values (?, ?, ?, ?)",
            [
                ("list-inbox", "Inbox", 0, 0),
                ("list-projects", "Projects", 0, 0),
                ("list-archived", "Archived", 0, 1),
                ("list-deleted", "Deleted", 1, 0),
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


def test_recurring_filter_returns_only_recurring_tasks(fake_2do_db: Path) -> None:
    with sqlite3.connect(fake_2do_db) as connection:
        _insert_task(
            connection,
            primid=4,
            uid="task-recurring",
            title="Recurring task",
            repeatvalue=1,
            repeattype=4,
        )

    recurring = server._get_tasks(server.TaskFilters(recurring=True))
    assert [task.title for task in recurring] == ["Recurring task"]


def test_one_off_filter_excludes_recurring_tasks(fake_2do_db: Path) -> None:
    with sqlite3.connect(fake_2do_db) as connection:
        _insert_task(
            connection,
            primid=4,
            uid="task-recurring",
            title="Recurring task",
            repeatvalue=1,
            repeattype=4,
        )

    titles = [task.title for task in server._get_tasks(server.TaskFilters(recurring=False))]
    assert "Recurring task" not in titles
    assert "Active task" in titles


def test_overdue_window_ends_at_start_of_today() -> None:
    due_from, due_before = server._overdue_window()

    assert due_from is None
    assert due_before == server._local_start_of_day(server._local_today())


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


def test_has_due_date_filter_excludes_tasks_without_due_dates(fake_2do_db: Path) -> None:
    with sqlite3.connect(fake_2do_db) as connection:
        _insert_task(
            connection,
            primid=4,
            uid="task-dated",
            title="Dated task",
            duedate=DUE_AT,
        )

    tasks = server._get_tasks(server.TaskFilters(has_due_date=True))

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
        (None, ("calendars", "isdeleted")),
        (None, ("calendars", "isarchived")),
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
    monkeypatch.setattr(server, "_get_lists", lambda: [])

    result = server.open_list("Work & Home")

    assert opened_urls == ["twodo://x-callback-url/showlist?name=Work%20%26%20Home"]
    assert result.url == "twodo://x-callback-url/showlist?name=Work%20%26%20Home"
    assert result.opened is True


def test_open_list_matches_list_name_case_insensitively(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(server, "open_url", opened_urls.append)

    result = server.open_list("inbox")

    assert opened_urls == ["twodo://x-callback-url/showlist?name=Inbox"]
    assert result.url == "twodo://x-callback-url/showlist?name=Inbox"
    assert result.opened is True


def test_open_list_falls_back_to_requested_name_when_lists_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(server, "open_url", opened_urls.append)
    monkeypatch.setattr(server, "_get_lists", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

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


def test_require_list_name_matches_case_insensitively(fake_2do_db: Path) -> None:
    assert server._require_list_name("inbox") == "Inbox"


def test_require_list_name_rejects_unknown_list(fake_2do_db: Path) -> None:
    with pytest.raises(ValueError, match="2Do list not found: Missing"):
        server._require_list_name("Missing")


def test_require_list_name_propagates_list_lookup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server,
        "_get_lists",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        server._require_list_name("Inbox")


def test_task_draft_resolves_list_and_normalizes_fields(fake_2do_db: Path) -> None:
    draft = server._task_draft(
        title=" Buy milk ",
        notes=None,
        list_name="inbox",
        due_date=None,
        tags=[" Home "],
        repeat=None,
    )

    assert draft.title == "Buy milk"
    assert draft.list_name == "Inbox"
    assert draft.tags == ["Home"]


def test_get_task_returns_exact_uid(fake_2do_db: Path) -> None:
    task = server._get_task("task-active")

    assert task is not None
    assert task.uuid == "task-active"
    assert task.title == "Active task"


def test_require_open_task_rejects_unknown_uid(fake_2do_db: Path) -> None:
    with pytest.raises(ValueError, match="2Do task not found: missing-task"):
        server._require_open_task("missing-task")


def test_require_open_task_rejects_completed_task(rich_2do_db: Path) -> None:
    with pytest.raises(ValueError, match="Task is already complete: Completed task"):
        server._require_open_task("task-completed")


def test_task_completion_preview_identifies_exact_task(fake_2do_db: Path) -> None:
    task = server._require_open_task("task-active")

    assert server.task_completion_preview(task) == (
        "Title: Active task\nList: Inbox\nUID: task-active"
    )


def test_open_task_quick_entry_opens_prefilled_add_url(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(server, "open_url", opened_urls.append)

    result = server.open_task_quick_entry(
        title="Buy milk",
        notes="Whole milk",
        list_name="inbox",
        tags=["Home"],
        repeat=None,
    )

    assert opened_urls == [
        "twodo://x-callback-url/add?"
        "task=Buy%20milk"
        "&note=Whole%20milk"
        "&forlist=Inbox"
        "&tags=Home"
        "&ignoredefaults=1"
        "&usequickentry=1"
    ]
    assert result.url == opened_urls[0]
    assert result.opened is True


class _FakeContext:
    def __init__(
        self,
        *,
        elicitation: object | None,
        response: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.session = SimpleNamespace(
            client_params=SimpleNamespace(
                capabilities=SimpleNamespace(elicitation=elicitation),
            )
        )
        self.response = response
        self.error = error
        self.calls: list[tuple[str, type[bool], str | None]] = []

    async def elicit(
        self,
        message: str,
        response_type: type[bool],
        *,
        response_title: str | None = None,
    ) -> object:
        self.calls.append((message, response_type, response_title))
        if self.error is not None:
            raise self.error
        return self.response


def _form_elicitation() -> SimpleNamespace:
    return SimpleNamespace(form=SimpleNamespace())


def _created_result() -> TaskCreationResult:
    return TaskCreationResult(
        status=TaskCreationStatus.CREATED,
        uid="task-123",
        task_url="twodo://x-callback-url/showtask?uid=task-123",
        message="Created task.",
    )


def test_create_task_uses_form_elicitation_when_supported(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _FakeContext(
        elicitation=_form_elicitation(),
        response=AcceptedElicitation(data=True),
    )
    created_drafts = []
    monkeypatch.setattr(
        server,
        "create_task_direct",
        lambda draft: created_drafts.append(draft) or _created_result(),
    )
    monkeypatch.setattr(
        server,
        "confirm_action_native",
        lambda _preview, **_kwargs: pytest.fail("native confirmation should not be used"),
    )

    result = asyncio.run(
        server.create_task(
            title="Buy milk",
            list_name="inbox",
            tags=["Home"],
            ctx=context,
        )
    )

    assert result.status is TaskCreationStatus.CREATED
    assert [draft.list_name for draft in created_drafts] == ["Inbox"]
    assert context.calls == [
        (
            "Title: Buy milk\nList: Inbox\nTags: Home",
            bool,
            "Create this task?",
        )
    ]


@pytest.mark.parametrize(
    "response",
    [
        AcceptedElicitation(data=False),
        DeclinedElicitation(),
        CancelledElicitation(),
    ],
)
def test_create_task_stops_when_elicitation_is_not_accepted(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: object,
) -> None:
    context = _FakeContext(elicitation=_form_elicitation(), response=response)
    monkeypatch.setattr(
        server,
        "create_task_direct",
        lambda _draft: pytest.fail("task should not be created"),
    )
    monkeypatch.setattr(
        server,
        "confirm_action_native",
        lambda _preview, **_kwargs: pytest.fail("native confirmation should not be used"),
    )

    result = asyncio.run(server.create_task(title="Buy milk", ctx=context))

    assert result.status is TaskCreationStatus.CANCELLED


def test_create_task_fails_closed_when_elicitation_errors(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _FakeContext(
        elicitation=_form_elicitation(),
        error=RuntimeError("client disconnected"),
    )
    monkeypatch.setattr(
        server,
        "create_task_direct",
        lambda _draft: pytest.fail("task should not be created"),
    )
    monkeypatch.setattr(
        server,
        "confirm_action_native",
        lambda _preview, **_kwargs: pytest.fail("native fallback should not be used"),
    )

    result = asyncio.run(server.create_task(title="Buy milk", ctx=context))

    assert result.status is TaskCreationStatus.FAILED
    assert result.message == "Could not confirm task creation: client disconnected"


def test_create_task_uses_native_confirmation_without_elicitation(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _FakeContext(elicitation=None)
    monkeypatch.setattr(
        server,
        "confirm_task_native",
        lambda _draft: ConfirmationResult(
            status=ConfirmationStatus.CONFIRMED,
            message="Task creation confirmed.",
        ),
    )
    monkeypatch.setattr(server, "create_task_direct", lambda _draft: _created_result())

    result = asyncio.run(server.create_task(title="Buy milk", ctx=context))

    assert result.status is TaskCreationStatus.CREATED
    assert context.calls == []


@pytest.mark.parametrize(
    ("confirmation", "expected_status"),
    [
        (
            ConfirmationResult(
                status=ConfirmationStatus.CANCELLED,
                message="Task creation cancelled.",
            ),
            TaskCreationStatus.CANCELLED,
        ),
        (
            ConfirmationResult(
                status=ConfirmationStatus.FAILED,
                message="Could not display confirmation.",
            ),
            TaskCreationStatus.FAILED,
        ),
    ],
)
def test_create_task_stops_when_native_confirmation_does_not_confirm(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: ConfirmationResult,
    expected_status: TaskCreationStatus,
) -> None:
    context = _FakeContext(elicitation=None)
    monkeypatch.setattr(server, "confirm_task_native", lambda _draft: confirmation)
    monkeypatch.setattr(
        server,
        "create_task_direct",
        lambda _draft: pytest.fail("task should not be created"),
    )

    result = asyncio.run(server.create_task(title="Buy milk", ctx=context))

    assert result.status is expected_status
    assert result.message == confirmation.message


def test_create_task_tool_annotations_describe_mutation() -> None:
    tool = asyncio.run(server.mcp.get_tool("create_task"))

    assert tool is not None
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.idempotentHint is False
    assert tool.annotations.openWorldHint is True


def _completed_result() -> TaskCompletionResult:
    return TaskCompletionResult(
        status=TaskCompletionStatus.COMPLETED,
        uid="task-active",
        task_url="twodo://x-callback-url/showtask?uid=task-active",
        message="Completed task.",
    )


def test_complete_task_uses_form_elicitation_when_supported(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _FakeContext(
        elicitation=_form_elicitation(),
        response=AcceptedElicitation(data=True),
    )
    completed_uids: list[str] = []
    monkeypatch.setattr(
        server,
        "complete_task_direct",
        lambda uid: completed_uids.append(uid) or _completed_result(),
    )
    monkeypatch.setattr(
        server,
        "confirm_task_native",
        lambda _draft: pytest.fail("native confirmation should not be used"),
    )

    result = asyncio.run(server.complete_task(uid="task-active", ctx=context))

    assert result.status is TaskCompletionStatus.COMPLETED
    assert completed_uids == ["task-active"]
    assert context.calls == [
        (
            "Title: Active task\nList: Inbox\nUID: task-active",
            bool,
            "Complete this task?",
        )
    ]


@pytest.mark.parametrize(
    "response",
    [
        AcceptedElicitation(data=False),
        DeclinedElicitation(),
        CancelledElicitation(),
    ],
)
def test_complete_task_stops_when_elicitation_is_not_accepted(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: object,
) -> None:
    context = _FakeContext(elicitation=_form_elicitation(), response=response)
    monkeypatch.setattr(
        server,
        "complete_task_direct",
        lambda _uid: pytest.fail("task should not be completed"),
    )
    monkeypatch.setattr(
        server,
        "confirm_task_native",
        lambda _draft: pytest.fail("native confirmation should not be used"),
    )

    result = asyncio.run(server.complete_task(uid="task-active", ctx=context))

    assert result.status is TaskCompletionStatus.CANCELLED


def test_complete_task_fails_closed_when_elicitation_errors(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _FakeContext(
        elicitation=_form_elicitation(),
        error=RuntimeError("client disconnected"),
    )
    monkeypatch.setattr(
        server,
        "complete_task_direct",
        lambda _uid: pytest.fail("task should not be completed"),
    )
    monkeypatch.setattr(
        server,
        "confirm_task_native",
        lambda _draft: pytest.fail("native fallback should not be used"),
    )

    result = asyncio.run(server.complete_task(uid="task-active", ctx=context))

    assert result.status is TaskCompletionStatus.FAILED
    assert result.message == "Could not confirm task completion: client disconnected"


def test_complete_task_uses_native_confirmation_without_elicitation(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _FakeContext(elicitation=None)
    monkeypatch.setattr(
        server,
        "confirm_action_native",
        lambda _preview, **_kwargs: ConfirmationResult(
            status=ConfirmationStatus.CONFIRMED,
            message="Task completion confirmed.",
        ),
    )
    monkeypatch.setattr(server, "complete_task_direct", lambda _uid: _completed_result())

    result = asyncio.run(server.complete_task(uid="task-active", ctx=context))

    assert result.status is TaskCompletionStatus.COMPLETED
    assert context.calls == []


@pytest.mark.parametrize(
    ("confirmation", "expected_status"),
    [
        (
            ConfirmationResult(
                status=ConfirmationStatus.CANCELLED,
                message="Task completion cancelled.",
            ),
            TaskCompletionStatus.CANCELLED,
        ),
        (
            ConfirmationResult(
                status=ConfirmationStatus.FAILED,
                message="Could not display confirmation.",
            ),
            TaskCompletionStatus.FAILED,
        ),
    ],
)
def test_complete_task_stops_when_native_confirmation_does_not_confirm(
    fake_2do_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: ConfirmationResult,
    expected_status: TaskCompletionStatus,
) -> None:
    context = _FakeContext(elicitation=None)
    monkeypatch.setattr(
        server,
        "confirm_action_native",
        lambda _preview, **_kwargs: confirmation,
    )
    monkeypatch.setattr(
        server,
        "complete_task_direct",
        lambda _uid: pytest.fail("task should not be completed"),
    )

    result = asyncio.run(server.complete_task(uid="task-active", ctx=context))

    assert result.status is expected_status
    assert result.message == confirmation.message


def test_complete_task_tool_annotations_describe_mutation() -> None:
    tool = asyncio.run(server.mcp.get_tool("complete_task"))

    assert tool is not None
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.idempotentHint is False
    assert tool.annotations.openWorldHint is True
