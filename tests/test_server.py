import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import _2do_mcp.server as server

CREATED_AT = datetime(2024, 1, 2, 12, 0, tzinfo=UTC).timestamp()


def _raw_tags(*tag_ids: str) -> str:
    parts: list[str] = []
    for tag_id in tag_ids:
        parts.extend(["", "", "", "", tag_id, "", ""])
    return server.TAG_DELIMITER.join(parts)


@pytest.fixture
def fake_2do_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "2do.db"

    with sqlite3.connect(db_path) as connection:
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
                archived integer
            );
            """
        )

        connection.executemany(
            "insert into calendars (uid, title) values (?, ?)",
            [("list-inbox", "Inbox")],
        )
        connection.executemany(
            "insert into tags (uid, tag, isdeleted) values (?, ?, ?)",
            [
                ("tag-work", "Work", 0),
                ("tag-deleted", "Deleted tag", 1),
            ],
        )
        connection.executemany(
            """
            insert into tasks (
                primid, uid, title, notes, creationstamp, duedate,
                completeddate, iscompleted, tags, calendaruid, isdeleted, archived
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    "task-active",
                    "Active task",
                    "Remember milk",
                    CREATED_AT,
                    server.NULL_DUE_DATE_SENTINEL,
                    0,
                    0,
                    _raw_tags("tag-work", "tag-deleted"),
                    "list-inbox",
                    0,
                    0,
                ),
                (
                    2,
                    "task-deleted",
                    "Deleted task",
                    None,
                    CREATED_AT,
                    0,
                    0,
                    0,
                    None,
                    "list-inbox",
                    1,
                    0,
                ),
                (
                    3,
                    "task-archived",
                    "Archived task",
                    None,
                    CREATED_AT,
                    0,
                    0,
                    0,
                    None,
                    "list-inbox",
                    0,
                    1,
                ),
            ],
        )

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(server, "_connect", connect)
    return db_path


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
    assert task.list.id == "list-inbox"
    assert task.list.name == "Inbox"
    assert [(tag.id, tag.name) for tag in task.tags] == [("tag-work", "Work")]
