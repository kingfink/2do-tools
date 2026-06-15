import argparse
import json
import sys
from datetime import date, datetime
from textwrap import dedent

from . import render, server
from .storage import backups_db_dir, backups_db_path
from .task_creation import (
    RepeatPreset,
    TaskCompletionStatus,
    TaskCreationStatus,
    complete_task_direct,
    create_task_direct,
    task_preview,
)

LIST_COLUMN_MAX_WIDTH = 20
TASK_COLUMN_MIN_WIDTH = 10
# Budget the Task column against the widest fixed labels: the "Status" header
# and a full ISO date in the Due column.
_STATUS_COLUMN_WIDTH = len("Status")
_DUE_COLUMN_WIDTH = len("0000-00-00")
_COLUMN_SEPARATOR_WIDTH = len("  ") * 3

REMOTE_CONNECTOR_DOCS = {
    "chatgpt": {
        "display_name": "ChatGPT",
        "public_url_label": "Authenticated ChatGPT MCP app URL",
        "docs_url": (
            "https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt"
        ),
        "next_steps": [
            "Expose the local endpoint only through HTTPS plus authentication.",
            "In ChatGPT developer mode, create a custom MCP app using the HTTPS URL.",
            "Scan the app's tools, then test with a prompt like: List my open 2Do tasks.",
        ],
    },
    "claude-cowork": {
        "display_name": "Claude Cowork",
        "public_url_label": "Authenticated Claude custom connector URL",
        "docs_url": (
            "https://support.claude.com/en/articles/"
            "11175166-get-started-with-custom-connectors-using-remote-mcp"
        ),
        "next_steps": [
            "Expose the local endpoint only through HTTPS plus authentication.",
            "In Claude, add a custom connector using the HTTPS URL.",
            "Test the connector with a prompt like: List my open 2Do tasks.",
        ],
    },
}

REMOTE_CONNECTOR_ALIASES = {
    "cowork": "claude-cowork",
}


def main(argv: list[str] | None = None) -> int:
    return _main(argv, prog="2do")


def _main(argv: list[str] | None, *, prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog)
    subparsers = parser.add_subparsers(dest="command")

    task_parser = subparsers.add_parser("task", help="Work with 2Do tasks.")
    task_subparsers = task_parser.add_subparsers(dest="task_command")
    task_list_parser = task_subparsers.add_parser("list", help="List 2Do tasks.")
    task_list_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    task_state = task_list_parser.add_mutually_exclusive_group()
    task_state.add_argument("--completed", action="store_true", help="List completed tasks.")
    task_state.add_argument("--all", action="store_true", help="List open and completed tasks.")
    task_list_parser.add_argument("--list", dest="list_name", help="Filter by list name.")
    task_list_parser.add_argument("--list-id", help="Filter by list ID.")
    task_list_parser.add_argument("--tag", dest="tag_name", help="Filter by tag name.")
    task_list_parser.add_argument("--tag-id", help="Filter by tag ID.")
    task_list_parser.add_argument(
        "--due-from", type=_date_arg, help="Filter to tasks due on or after YYYY-MM-DD."
    )
    task_list_parser.add_argument(
        "--due-before", type=_date_arg, help="Filter to tasks due before YYYY-MM-DD."
    )
    task_list_parser.add_argument(
        "--completed-from",
        type=_date_arg,
        help="Filter to tasks completed on or after YYYY-MM-DD.",
    )
    task_list_parser.add_argument(
        "--completed-before",
        type=_date_arg,
        help="Filter to tasks completed before YYYY-MM-DD.",
    )
    task_list_parser.add_argument(
        "--has-due-date", action="store_true", help="Filter to tasks with any due date."
    )
    due_window = task_list_parser.add_mutually_exclusive_group()
    due_window.add_argument("--due-today", action="store_true", help="Filter to tasks due today.")
    due_window.add_argument(
        "--due-this-week",
        action="store_true",
        help="Filter to tasks due during the current calendar week.",
    )
    due_window.add_argument(
        "--overdue", action="store_true", help="Filter to open tasks due before today."
    )
    recurrence = task_list_parser.add_mutually_exclusive_group()
    recurrence.add_argument("--recurring", action="store_true", help="Filter to recurring tasks.")
    recurrence.add_argument("--one-off", action="store_true", help="Filter to non-recurring tasks.")
    task_list_parser.add_argument("--query", help="Search task title, notes, list, and tags.")
    task_list_parser.add_argument("--limit", type=int, default=1000, help="Maximum tasks to print.")
    task_list_parser.add_argument(
        "--no-hyperlinks",
        action="store_true",
        help="Print plain task titles instead of clickable links.",
    )
    task_open_parser = task_subparsers.add_parser("open", help="Open a 2Do task by UID.")
    task_open_parser.add_argument("uid")
    task_complete_parser = task_subparsers.add_parser(
        "complete",
        help="Complete one 2Do task after terminal confirmation.",
    )
    task_complete_parser.add_argument("uid")
    task_quick_entry_parser = task_subparsers.add_parser(
        "quick-entry",
        help="Open a pre-filled Quick Entry editor in 2Do.",
    )
    _add_task_creation_arguments(task_quick_entry_parser)
    task_create_parser = task_subparsers.add_parser(
        "create",
        help="Create a 2Do task after terminal confirmation.",
    )
    _add_task_creation_arguments(task_create_parser)

    list_parser = subparsers.add_parser("list", help="Work with 2Do lists.")
    list_subparsers = list_parser.add_subparsers(dest="list_command")
    list_list_parser = list_subparsers.add_parser("list", help="List 2Do lists.")
    list_list_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    list_open_parser = list_subparsers.add_parser("open", help="Open a 2Do list by name.")
    list_open_parser.add_argument("name")

    tag_parser = subparsers.add_parser("tag", help="Work with 2Do tags.")
    tag_subparsers = tag_parser.add_subparsers(dest="tag_command")
    tag_list_parser = tag_subparsers.add_parser("list", help="List 2Do tags.")
    tag_list_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    search_parser = subparsers.add_parser("search", help="Work with 2Do searches.")
    search_subparsers = search_parser.add_subparsers(dest="search_command")
    search_open_parser = search_subparsers.add_parser("open", help="Open a 2Do search.")
    search_open_parser.add_argument("query")

    mcp_parser = subparsers.add_parser("mcp", help="Run or configure the MCP server.")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    serve_parser = mcp_subparsers.add_parser("serve")
    serve_parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "http", "sse"],
        default="stdio",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)

    subparsers.add_parser("refresh")
    subparsers.add_parser("doctor")

    connect_parser = mcp_subparsers.add_parser(
        "connect",
        help="Print remote connector setup guidance for ChatGPT or Claude Cowork.",
    )
    connect_parser.add_argument(
        "client",
        choices=sorted([*REMOTE_CONNECTOR_DOCS, *REMOTE_CONNECTOR_ALIASES]),
    )
    connect_parser.add_argument("--host", default="127.0.0.1")
    connect_parser.add_argument("--port", type=int, default=8765)
    connect_parser.add_argument(
        "--public-url",
        help="Optional public HTTPS MCP URL to include in the printed guidance.",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "task":
        if args.task_command == "list":
            return _list_tasks(args, task_list_parser)

        if args.task_command == "open":
            return _open_task(args)

        if args.task_command == "complete":
            return _complete_task(args)

        if args.task_command == "quick-entry":
            return _open_task_quick_entry(args)

        if args.task_command == "create":
            return _create_task(args)

        task_parser.print_help()
        return 0

    if args.command == "list":
        if args.list_command == "list":
            return _list_lists(args)

        if args.list_command == "open":
            return _open_list(args)

        list_parser.print_help()
        return 0

    if args.command == "tag":
        if args.tag_command == "list":
            return _list_tags(args)

        tag_parser.print_help()
        return 0

    if args.command == "search":
        if args.search_command == "open":
            return _open_search(args)

        search_parser.print_help()
        return 0

    if args.command == "mcp":
        if args.mcp_command == "serve":
            return _serve(args.transport, host=args.host, port=args.port)

        if args.mcp_command == "connect":
            return _connect(args.client, host=args.host, port=args.port, public_url=args.public_url)

        mcp_parser.print_help()
        return 0

    if args.command == "refresh":
        refreshed = server.refresh_backup()
        status = "Refreshed" if refreshed else "Backup already current"
        print(f"{status} at {backups_db_path()}")
        return 0

    if args.command == "doctor":
        return _doctor()

    parser.error(f"unknown command: {args.command}")
    return 2


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _add_task_creation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("title")
    parser.add_argument("--notes")
    parser.add_argument("--list", dest="list_name")
    parser.add_argument("--due", dest="due_date", type=_date_arg)
    parser.add_argument("--tag", dest="tags", action="append")
    parser.add_argument(
        "--repeat",
        choices=[preset.value for preset in RepeatPreset],
    )


def _task_creation_kwargs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "title": args.title,
        "notes": args.notes,
        "list_name": args.list_name,
        "due_date": args.due_date,
        "tags": args.tags,
        "repeat": RepeatPreset(args.repeat) if args.repeat is not None else None,
    }


def _list_tasks(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    completed = None if args.all else args.completed
    due_from, due_before = _resolve_due_bounds(args, parser)
    completed_from, completed_before = server._date_range_bounds(
        args.completed_from,
        args.completed_before,
    )
    recurring = True if args.recurring else False if args.one_off else None

    tasks = server._get_tasks(
        server.TaskFilters(
            completed=completed,
            list_id=args.list_id,
            list_name=args.list_name,
            tag_id=args.tag_id,
            tag_name=args.tag_name,
            due_from=due_from,
            due_before=due_before,
            has_due_date=args.has_due_date,
            completed_from=completed_from,
            completed_before=completed_before,
            recurring=recurring,
            query=args.query,
            limit=args.limit,
        )
    )

    if args.json:
        _print_json(tasks)
        return 0

    _print_task_table(tasks, hyperlinks=_hyperlinks_enabled(no_hyperlinks=args.no_hyperlinks))

    return 0


def _resolve_due_bounds(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> tuple[datetime | None, datetime | None]:
    uses_manual_due_filter = (
        args.due_from is not None or args.due_before is not None or args.has_due_date
    )
    if (args.due_today or args.due_this_week or args.overdue) and uses_manual_due_filter:
        parser.error(
            "--due-today/--due-this-week/--overdue cannot be combined with "
            "--due-from/--due-before/--has-due-date"
        )

    if args.due_today:
        return server._today_window()
    if args.due_this_week:
        return server._calendar_week_window()
    if args.overdue:
        return server._overdue_window()
    return server._date_range_bounds(args.due_from, args.due_before)


def _hyperlinks_enabled(*, no_hyperlinks: bool) -> bool:
    return not no_hyperlinks and sys.stdout.isatty()


def _open_task(args: argparse.Namespace) -> int:
    result = server.open_task(args.uid)
    print(result.url)
    return 0


def _confirm_in_terminal(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False

    try:
        answer = input(prompt)
    except EOFError:
        return False

    return answer.strip().casefold() in {"y", "yes"}


def _complete_task(args: argparse.Namespace) -> int:
    task = server._require_open_task(args.uid)
    print(server.task_completion_preview(task))

    if not _confirm_in_terminal("Complete this task? [y/N] "):
        print("Task completion cancelled.")
        return 0

    result = complete_task_direct(task.uuid)
    if result.status is TaskCompletionStatus.COMPLETED:
        print(f"Completed task {result.uid} - {result.task_url}")
        return 0
    if result.status is TaskCompletionStatus.CANCELLED:
        print(result.message)
        return 0

    print(result.message, file=sys.stderr)
    return 1


def _open_task_quick_entry(args: argparse.Namespace) -> int:
    result = server.open_task_quick_entry(**_task_creation_kwargs(args))
    print(result.url)
    return 0


def _create_task(args: argparse.Namespace) -> int:
    draft = server._task_draft(**_task_creation_kwargs(args))
    print(task_preview(draft))

    if not _confirm_in_terminal("Create this task? [y/N] "):
        print("Task creation cancelled.")
        return 0

    result = create_task_direct(draft)
    if result.status is TaskCreationStatus.CREATED:
        print(f"Created task {result.uid} - {result.task_url}")
        return 0
    if result.status is TaskCreationStatus.CANCELLED:
        print(result.message)
        return 0

    print(result.message, file=sys.stderr)
    return 1


def _list_lists(args: argparse.Namespace) -> int:
    task_lists = server._get_lists()

    if args.json:
        _print_json(task_lists)
        return 0

    for task_list in task_lists:
        print(f"{task_list.name} - {task_list.url}")

    return 0


def _open_list(args: argparse.Namespace) -> int:
    result = server.open_list(args.name)
    print(result.url)
    return 0


def _list_tags(args: argparse.Namespace) -> int:
    tags = server._get_tags()

    if args.json:
        _print_json(tags)
        return 0

    for tag in tags:
        print(tag.name)

    return 0


def _open_search(args: argparse.Namespace) -> int:
    result = server.open_search(args.query)
    print(result.url)
    return 0


def _print_json(items: list[object]) -> None:
    payload = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in items
    ]
    print(json.dumps(payload, indent=2))


def _print_task_table(tasks: list[server.Task], *, hyperlinks: bool) -> None:
    if not tasks:
        return

    list_width = min(
        LIST_COLUMN_MAX_WIDTH,
        max(len("List"), *(len(task.list.name) for task in tasks)),
    )
    fixed_width = _STATUS_COLUMN_WIDTH + list_width + _DUE_COLUMN_WIDTH + _COLUMN_SEPARATOR_WIDTH
    task_width = max(render.terminal_width() - fixed_width, TASK_COLUMN_MIN_WIDTH)

    rows = [_task_table_row(task, list_width, task_width) for task in tasks]
    for line in render.render_table(["Status", "List", "Task", "Due"], rows, hyperlinks=hyperlinks):
        print(line)


def _task_table_row(
    task: server.Task,
    list_width: int,
    task_width: int,
) -> list[render.Cell]:
    return [
        render.Cell("[x]" if task.completed else "[ ]"),
        render.Cell(render.truncate(task.list.name, list_width)),
        render.Cell(render.truncate(task.title, task_width), url=task.url),
        render.Cell(task.date_due.date().isoformat() if task.date_due is not None else ""),
    ]


def _serve(transport: str, *, host: str = "127.0.0.1", port: int = 8765) -> int:
    server.ensure_backup_db_current()

    kwargs = {}
    if transport != "stdio":
        kwargs = {"host": host, "port": port}

    server.mcp.run(transport=transport, **kwargs)
    return 0


def _doctor() -> int:
    print("2do doctor")
    print(f"Backup directory: {backups_db_dir()}")

    candidates = server.discover_candidate_dbs()
    if not candidates:
        print("No 2Do database candidates found.", file=sys.stderr)
        return 1

    print("2Do database candidates:")
    for candidate in candidates:
        print(f"  - {candidate}")

    try:
        server.ensure_backup_db_current()
    except Exception as exc:
        print(f"Backup check failed: {exc}", file=sys.stderr)
        return 1

    print(f"Backup database: {backups_db_path()}")
    return 0


def _connect(
    client: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    public_url: str | None = None,
) -> int:
    client_key = REMOTE_CONNECTOR_ALIASES.get(client, client)
    connector = REMOTE_CONNECTOR_DOCS[client_key]
    local_endpoint = f"http://{host}:{port}/mcp"
    public_endpoint = public_url or "https://your-tunnel.example.com/mcp"

    print(
        dedent(
            f"""
            2Do Tools remote connector helper: {connector["display_name"]}

            Start the local Streamable HTTP server:

              2do mcp serve --transport streamable-http --host {host} --port {port}

            Local endpoint:

              {local_endpoint}

            {connector["public_url_label"]}:

              {public_endpoint}

            Important:
              ChatGPT and Claude Cowork cannot reach your plain localhost URL directly.
              The HTTP transport does not add authentication by itself. Put it
              behind HTTPS and authentication that restricts access to trusted
              users only. Do not expose it publicly or rely on a secret URL.

            Next steps:
            """
        ).strip()
    )

    for step in connector["next_steps"]:
        print(f"  - {step}")

    print(f"\nDocs: {connector['docs_url']}")
    return 0
