import json
from datetime import UTC, datetime

import pytest

from _2do_tools import cli, server


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
