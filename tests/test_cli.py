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


def test_2do_tasks_lists_open_tasks_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured_filters: list[server.TaskFilters] = []

    def get_tasks(filters: server.TaskFilters) -> list[server.Task]:
        captured_filters.append(filters)
        return [_task()]

    monkeypatch.setattr(cli.server, "_get_tasks", get_tasks)

    assert cli.main(["tasks"]) == 0

    assert captured_filters == [server.TaskFilters(completed=False)]
    assert capsys.readouterr().out == "[ ] Active task - Inbox - Work\n"


def test_2do_tasks_applies_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_filters: list[server.TaskFilters] = []

    def get_tasks(filters: server.TaskFilters) -> list[server.Task]:
        captured_filters.append(filters)
        return []

    monkeypatch.setattr(cli.server, "_get_tasks", get_tasks)

    assert (
        cli.main(
            [
                "tasks",
                "--completed",
                "--list",
                "Projects",
                "--tag",
                "Home",
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
            query="invoice",
            limit=12,
        )
    ]


def test_2do_tasks_prints_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.server, "_get_tasks", lambda filters: [_task()])

    assert cli.main(["tasks", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output[0]["title"] == "Active task"
    assert output[0]["list"]["name"] == "Inbox"


def test_2do_lists_prints_lists(
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

    assert cli.main(["lists"]) == 0

    assert capsys.readouterr().out == "Inbox - twodo://x-callback-url/showlist?name=Inbox\n"


def test_2do_without_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0

    assert capsys.readouterr().out.startswith("usage: 2do ")


def test_2do_connect_recommends_2do_serve(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["connect", "chatgpt"]) == 0

    assert "2do serve --transport streamable-http" in capsys.readouterr().out
