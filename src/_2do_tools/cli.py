import argparse
import json
import sys
from textwrap import dedent

from . import server
from .storage import backups_db_dir, backups_db_path

REMOTE_CONNECTOR_DOCS = {
    "chatgpt": {
        "display_name": "ChatGPT",
        "public_url_label": "ChatGPT MCP app URL",
        "docs_url": (
            "https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt"
        ),
        "next_steps": [
            "Expose the local endpoint through a trusted HTTPS tunnel or hosted deployment.",
            "In ChatGPT developer mode, create a custom MCP app using the HTTPS URL.",
            "Scan the app's tools, then test with a prompt like: List my open 2Do tasks.",
        ],
    },
    "claude-cowork": {
        "display_name": "Claude Cowork",
        "public_url_label": "Claude custom connector URL",
        "docs_url": (
            "https://support.claude.com/en/articles/"
            "11175166-get-started-with-custom-connectors-using-remote-mcp"
        ),
        "next_steps": [
            "Expose the local endpoint through a trusted HTTPS tunnel or hosted deployment.",
            "In Claude, add a custom connector using the HTTPS URL.",
            "Test the connector with a prompt like: List my open 2Do tasks.",
        ],
    },
}

REMOTE_CONNECTOR_ALIASES = {
    "cowork": "claude-cowork",
}


def main(argv: list[str] | None = None) -> int:
    return _main(argv, prog="2do-tools", serve_by_default=True)


def main_2do(argv: list[str] | None = None) -> int:
    return _main(argv, prog="2do", serve_by_default=False)


def _main(argv: list[str] | None, *, prog: str, serve_by_default: bool) -> int:
    parser = argparse.ArgumentParser(prog=prog)
    subparsers = parser.add_subparsers(dest="command")

    tasks_parser = subparsers.add_parser("tasks", help="List 2Do tasks.")
    tasks_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    tasks_state = tasks_parser.add_mutually_exclusive_group()
    tasks_state.add_argument("--completed", action="store_true", help="List completed tasks.")
    tasks_state.add_argument("--all", action="store_true", help="List open and completed tasks.")
    tasks_parser.add_argument("--list", dest="list_name", help="Filter by list name.")
    tasks_parser.add_argument("--list-id", help="Filter by list ID.")
    tasks_parser.add_argument("--tag", dest="tag_name", help="Filter by tag name.")
    tasks_parser.add_argument("--tag-id", help="Filter by tag ID.")
    tasks_parser.add_argument("--query", help="Search task title, notes, list, and tags.")
    tasks_parser.add_argument("--limit", type=int, default=1000, help="Maximum tasks to print.")

    lists_parser = subparsers.add_parser("lists", help="List 2Do lists.")
    lists_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    tags_parser = subparsers.add_parser("tags", help="List 2Do tags.")
    tags_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "http", "sse"],
        default="stdio",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)

    subparsers.add_parser("refresh")
    subparsers.add_parser("doctor")

    connect_parser = subparsers.add_parser(
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
        if serve_by_default:
            return _serve("stdio")

        parser.print_help()
        return 0

    if args.command == "tasks":
        return _list_tasks(args)

    if args.command == "lists":
        return _list_lists(args)

    if args.command == "tags":
        return _list_tags(args)

    if args.command == "serve":
        return _serve(args.transport, host=args.host, port=args.port)

    if args.command == "refresh":
        refreshed = server.refresh_backup()
        status = "Refreshed" if refreshed else "Backup already current"
        print(f"{status} at {backups_db_path()}")
        return 0

    if args.command == "doctor":
        return _doctor()

    if args.command == "connect":
        return _connect(args.client, host=args.host, port=args.port, public_url=args.public_url)

    parser.error(f"unknown command: {args.command}")
    return 2


def _list_tasks(args: argparse.Namespace) -> int:
    completed = None if args.all else args.completed
    tasks = server._get_tasks(
        server.TaskFilters(
            completed=completed,
            list_id=args.list_id,
            list_name=args.list_name,
            tag_id=args.tag_id,
            tag_name=args.tag_name,
            query=args.query,
            limit=args.limit,
        )
    )

    if args.json:
        _print_json(tasks)
        return 0

    for task in tasks:
        print(_format_task(task))

    return 0


def _list_lists(args: argparse.Namespace) -> int:
    task_lists = server._get_lists()

    if args.json:
        _print_json(task_lists)
        return 0

    for task_list in task_lists:
        print(f"{task_list.name} - {task_list.url}")

    return 0


def _list_tags(args: argparse.Namespace) -> int:
    tags = server._get_tags()

    if args.json:
        _print_json(tags)
        return 0

    for tag in tags:
        print(tag.name)

    return 0


def _print_json(items: list[object]) -> None:
    payload = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in items
    ]
    print(json.dumps(payload, indent=2))


def _format_task(task: server.Task) -> str:
    status = "[x]" if task.completed else "[ ]"
    parts = [f"{status} {task.title}", task.list.name]

    if task.date_due is not None:
        parts.append(f"due {task.date_due.date().isoformat()}")

    if task.tags:
        parts.append(", ".join(tag.name for tag in task.tags))

    return " - ".join(parts)


def _serve(transport: str, *, host: str = "127.0.0.1", port: int = 8765) -> int:
    server.ensure_backup_db_current()

    kwargs = {}
    if transport != "stdio":
        kwargs = {"host": host, "port": port}

    server.mcp.run(transport=transport, **kwargs)
    return 0


def _doctor() -> int:
    print("2do-tools doctor")
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

              2do-tools serve --transport streamable-http --host {host} --port {port}

            Local endpoint:

              {local_endpoint}

            {connector["public_url_label"]}:

              {public_endpoint}

            Important:
              ChatGPT and Claude Cowork cannot reach your plain localhost URL directly.
              Use a trusted HTTPS tunnel or hosted deployment, and only share it if you
              are comfortable exposing your local 2Do task data through that endpoint.

            Next steps:
            """
        ).strip()
    )

    for step in connector["next_steps"]:
        print(f"  - {step}")

    print(f"\nDocs: {connector['docs_url']}")
    return 0
