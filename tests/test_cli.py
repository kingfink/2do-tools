import json
from datetime import UTC, date, datetime

import pytest

from _2do_tools import cli, server
from _2do_tools.task_creation import (
    RepeatPreset,
    TaskCreationResult,
    TaskCreationStatus,
    TaskDraft,
)


def _task(*, title: str = "Active task", completed: bool = False) -> server.Task:
    return server.Task(
        id=1,
        uuid="task-active",
        url="twodo://x-callback-url/showtask?uid=task-active",
        title=title,
        notes=None,
        date_created=datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
        date_due=None,
        date_completed=None,
        completed=completed,
        list=server.TaskList(
            id="list-inbox",
            name="Inbox",
            url="twodo://x-callback-url/showlist?name=Inbox",
        ),
        tags=[server.Tag(id="tag-work", name="Work")],
    )


def test_2do_task_lists_open_tasks_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured_filters: list[server.TaskFilters] = []

    def get_tasks(filters: server.TaskFilters) -> list[server.Task]:
        captured_filters.append(filters)
        return [_task()]

    monkeypatch.setattr(cli.server, "_get_tasks", get_tasks)

    assert cli.main(["task", "list"]) == 0

    assert captured_filters == [server.TaskFilters(completed=False)]
    assert capsys.readouterr().out == (
        "Status  List   Task         Due\n"
        "------  -----  -----------  ---\n"
        "[ ]     Inbox  Active task\n"
    )


def test_2do_task_applies_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_filters: list[server.TaskFilters] = []

    def get_tasks(filters: server.TaskFilters) -> list[server.Task]:
        captured_filters.append(filters)
        return []

    monkeypatch.setattr(cli.server, "_get_tasks", get_tasks)

    assert (
        cli.main(
            [
                "task",
                "list",
                "--completed",
                "--list",
                "Projects",
                "--tag",
                "Home",
                "--due-from",
                "2024-01-01",
                "--due-before",
                "2024-02-01",
                "--completed-from",
                "2024-03-01",
                "--completed-before",
                "2024-04-01",
                "--has-due-date",
                "--query",
                "invoice",
                "--limit",
                "12",
            ]
        )
        == 0
    )

    assert captured_filters == [
        server.TaskFilters(
            completed=True,
            list_name="Projects",
            tag_name="Home",
            due_from=datetime(2024, 1, 1).astimezone(),
            due_before=datetime(2024, 2, 1).astimezone(),
            completed_from=datetime(2024, 3, 1).astimezone(),
            completed_before=datetime(2024, 4, 1).astimezone(),
            has_due_date=True,
            query="invoice",
            limit=12,
        )
    ]


def _capture_filters(monkeypatch: pytest.MonkeyPatch) -> list[server.TaskFilters]:
    captured: list[server.TaskFilters] = []
    monkeypatch.setattr(
        cli.server,
        "_get_tasks",
        lambda filters: captured.append(filters) or [],
    )
    return captured


def test_due_today_flag_uses_today_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_filters(monkeypatch)

    assert cli.main(["task", "list", "--due-today"]) == 0

    due_from, due_before = server._today_window()
    assert captured == [
        server.TaskFilters(completed=False, due_from=due_from, due_before=due_before)
    ]


def test_due_this_week_flag_uses_week_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_filters(monkeypatch)

    assert cli.main(["task", "list", "--due-this-week"]) == 0

    due_from, due_before = server._calendar_week_window()
    assert captured == [
        server.TaskFilters(completed=False, due_from=due_from, due_before=due_before)
    ]


def test_overdue_flag_uses_overdue_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_filters(monkeypatch)

    assert cli.main(["task", "list", "--overdue"]) == 0

    _due_from, due_before = server._overdue_window()
    assert captured == [server.TaskFilters(completed=False, due_before=due_before)]


def test_recurring_flag_filters_recurring_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_filters(monkeypatch)

    assert cli.main(["task", "list", "--recurring"]) == 0

    assert captured == [server.TaskFilters(completed=False, recurring=True)]


def test_one_off_flag_filters_non_recurring_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_filters(monkeypatch)

    assert cli.main(["task", "list", "--one-off"]) == 0

    assert captured == [server.TaskFilters(completed=False, recurring=False)]


def test_due_window_flags_are_mutually_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_filters(monkeypatch)

    with pytest.raises(SystemExit):
        cli.main(["task", "list", "--due-today", "--due-from", "2024-01-01"])


def test_recurring_and_one_off_are_mutually_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_filters(monkeypatch)

    with pytest.raises(SystemExit):
        cli.main(["task", "list", "--recurring", "--one-off"])


def test_task_table_truncates_long_titles_to_terminal_width(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    long_title = "Email the accountant about the overdue invoice and the receipts"
    monkeypatch.setattr(cli.server, "_get_tasks", lambda filters: [_task(title=long_title)])
    monkeypatch.setattr(cli.render, "terminal_width", lambda: 40)

    assert cli.main(["task", "list"]) == 0

    out = capsys.readouterr().out
    task_line = out.splitlines()[2]
    assert "..." in task_line
    assert len(task_line) <= 40
    assert long_title not in out


def test_hyperlinks_disabled_when_not_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False, raising=False)

    assert cli._hyperlinks_enabled(no_hyperlinks=False) is False


def test_hyperlinks_enabled_on_a_tty_unless_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)

    assert cli._hyperlinks_enabled(no_hyperlinks=False) is True
    assert cli._hyperlinks_enabled(no_hyperlinks=True) is False


def test_2do_task_prints_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.server, "_get_tasks", lambda filters: [_task()])

    assert cli.main(["task", "list", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output[0]["title"] == "Active task"
    assert output[0]["list"]["name"] == "Inbox"


def test_2do_list_prints_lists(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.server,
        "_get_lists",
        lambda: [
            server.TaskList(
                id="list-inbox",
                name="Inbox",
                url="twodo://x-callback-url/showlist?name=Inbox",
            )
        ],
    )

    assert cli.main(["list", "list"]) == 0

    assert capsys.readouterr().out == "Inbox - twodo://x-callback-url/showlist?name=Inbox\n"


def test_2do_tag_lists_tags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.server, "_get_tags", lambda: [server.Tag(id="tag-work", name="Work")])

    assert cli.main(["tag", "list"]) == 0

    assert capsys.readouterr().out == "Work\n"


def test_2do_task_open_opens_task(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.server,
        "open_task",
        lambda uid: server.OpenedUrl(url=f"twodo://x-callback-url/showtask?uid={uid}", opened=True),
    )

    assert cli.main(["task", "open", "task-active"]) == 0

    assert capsys.readouterr().out == "twodo://x-callback-url/showtask?uid=task-active\n"


def test_2do_list_open_opens_list(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.server,
        "open_list",
        lambda name: server.OpenedUrl(
            url=f"twodo://x-callback-url/showlist?name={name}", opened=True
        ),
    )

    assert cli.main(["list", "open", "Inbox"]) == 0

    assert capsys.readouterr().out == "twodo://x-callback-url/showlist?name=Inbox\n"


def test_2do_search_open_opens_search(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.server,
        "open_search",
        lambda text: server.OpenedUrl(
            url=f"twodo://x-callback-url/search?text={text}", opened=True
        ),
    )

    assert cli.main(["search", "open", "invoice"]) == 0

    assert capsys.readouterr().out == "twodo://x-callback-url/search?text=invoice\n"


def test_2do_without_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0

    assert capsys.readouterr().out.startswith("usage: 2do ")


def test_2do_connect_recommends_2do_serve(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["mcp", "connect", "chatgpt"]) == 0

    assert "2do mcp serve --transport streamable-http" in capsys.readouterr().out


def test_2do_task_quick_entry_passes_all_supported_fields(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, object]] = []

    def open_task_quick_entry(**kwargs: object) -> server.OpenedUrl:
        calls.append(kwargs)
        return server.OpenedUrl(url="twodo://x-callback-url/add?usequickentry=1", opened=True)

    monkeypatch.setattr(cli.server, "open_task_quick_entry", open_task_quick_entry)

    assert (
        cli.main(
            [
                "task",
                "quick-entry",
                "Buy milk",
                "--notes",
                "Whole milk",
                "--list",
                "Inbox",
                "--due",
                "2026-06-20",
                "--tag",
                "Home",
                "--tag",
                "Errands",
                "--repeat",
                "weekly",
            ]
        )
        == 0
    )

    assert calls == [
        {
            "title": "Buy milk",
            "notes": "Whole milk",
            "list_name": "Inbox",
            "due_date": date(2026, 6, 20),
            "tags": ["Home", "Errands"],
            "repeat": RepeatPreset.WEEKLY,
        }
    ]
    assert capsys.readouterr().out == "twodo://x-callback-url/add?usequickentry=1\n"


class _InteractiveStdin:
    def isatty(self) -> bool:
        return True


class _NonInteractiveStdin:
    def isatty(self) -> bool:
        return False


def _draft() -> TaskDraft:
    return TaskDraft(
        title="Buy milk",
        notes="Whole milk",
        list_name="Inbox",
        due_date=date(2026, 6, 20),
        tags=["Home"],
        repeat=RepeatPreset.WEEKLY,
    )


def test_2do_task_create_confirms_and_prints_created_task(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    draft = _draft()
    draft_calls: list[dict[str, object]] = []
    created_drafts: list[TaskDraft] = []

    def task_draft(**kwargs: object) -> TaskDraft:
        draft_calls.append(kwargs)
        return draft

    monkeypatch.setattr(cli.server, "_task_draft", task_draft)
    monkeypatch.setattr(cli.sys, "stdin", _InteractiveStdin())
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    monkeypatch.setattr(
        cli,
        "create_task_direct",
        lambda value: (
            created_drafts.append(value)
            or TaskCreationResult(
                status=TaskCreationStatus.CREATED,
                uid="task-123",
                task_url="twodo://x-callback-url/showtask?uid=task-123",
                message="Created task.",
            )
        ),
    )

    assert (
        cli.main(
            [
                "task",
                "create",
                "Buy milk",
                "--notes",
                "Whole milk",
                "--due",
                "2026-06-20",
                "--tag",
                "Home",
                "--repeat",
                "weekly",
            ]
        )
        == 0
    )

    assert draft_calls == [
        {
            "title": "Buy milk",
            "notes": "Whole milk",
            "list_name": "Inbox",
            "due_date": date(2026, 6, 20),
            "tags": ["Home"],
            "repeat": RepeatPreset.WEEKLY,
        }
    ]
    assert created_drafts == [draft]
    assert capsys.readouterr().out == (
        "Title: Buy milk\n"
        "Notes: Whole milk\n"
        "List: Inbox\n"
        "Due: 2026-06-20\n"
        "Tags: Home\n"
        "Repeat: weekly\n"
        "Created task task-123 - twodo://x-callback-url/showtask?uid=task-123\n"
    )


@pytest.mark.parametrize("answer", ["", "n", "nope"])
def test_2do_task_create_cancels_for_non_affirmative_answer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    answer: str,
) -> None:
    monkeypatch.setattr(cli.server, "_task_draft", lambda **_kwargs: _draft())
    monkeypatch.setattr(cli.sys, "stdin", _InteractiveStdin())
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    monkeypatch.setattr(
        cli,
        "create_task_direct",
        lambda _draft: pytest.fail("task should not be created"),
    )

    assert cli.main(["task", "create", "Buy milk"]) == 0

    assert capsys.readouterr().out.endswith("Task creation cancelled.\n")


def test_2do_task_create_cancels_on_eof(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.server, "_task_draft", lambda **_kwargs: _draft())
    monkeypatch.setattr(cli.sys, "stdin", _InteractiveStdin())
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: (_ for _ in ()).throw(EOFError),
    )
    monkeypatch.setattr(
        cli,
        "create_task_direct",
        lambda _draft: pytest.fail("task should not be created"),
    )

    assert cli.main(["task", "create", "Buy milk"]) == 0

    assert capsys.readouterr().out.endswith("Task creation cancelled.\n")


def test_2do_task_create_cancels_for_non_interactive_stdin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.server, "_task_draft", lambda **_kwargs: _draft())
    monkeypatch.setattr(cli.sys, "stdin", _NonInteractiveStdin())
    monkeypatch.setattr(
        cli,
        "create_task_direct",
        lambda _draft: pytest.fail("task should not be created"),
    )

    assert cli.main(["task", "create", "Buy milk"]) == 0

    assert capsys.readouterr().out.endswith("Task creation cancelled.\n")


def test_2do_task_create_prints_callback_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.server, "_task_draft", lambda **_kwargs: _draft())
    monkeypatch.setattr(cli.sys, "stdin", _InteractiveStdin())
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    monkeypatch.setattr(
        cli,
        "create_task_direct",
        lambda _draft: TaskCreationResult(
            status=TaskCreationStatus.CANCELLED,
            message="Task creation cancelled.",
        ),
    )

    assert cli.main(["task", "create", "Buy milk"]) == 0

    assert capsys.readouterr().out.endswith("Task creation cancelled.\n")


def test_2do_task_create_prints_failure_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.server, "_task_draft", lambda **_kwargs: _draft())
    monkeypatch.setattr(cli.sys, "stdin", _InteractiveStdin())
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    monkeypatch.setattr(
        cli,
        "create_task_direct",
        lambda _draft: TaskCreationResult(
            status=TaskCreationStatus.FAILED,
            message="2Do could not create the task.",
        ),
    )

    assert cli.main(["task", "create", "Buy milk"]) == 1

    captured = capsys.readouterr()
    assert captured.out.startswith("Title: Buy milk\n")
    assert captured.err == "2Do could not create the task.\n"


def test_2do_task_create_has_no_confirmation_bypass() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["task", "create", "Buy milk", "--yes"])

    assert exc_info.value.code == 2
