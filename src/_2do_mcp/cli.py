import argparse
import sys

from . import server
from .storage import backups_db_dir, backups_db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="2do-mcp")
    subparsers = parser.add_subparsers(dest="command")

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

    args = parser.parse_args(argv)

    if args.command is None:
        return _serve("stdio")

    if args.command == "serve":
        return _serve(args.transport, host=args.host, port=args.port)

    if args.command == "refresh":
        refreshed = server.refresh_backup()
        status = "Refreshed" if refreshed else "Backup already current"
        print(f"{status} at {backups_db_path()}")
        return 0

    if args.command == "doctor":
        return _doctor()

    parser.error(f"unknown command: {args.command}")
    return 2


def _serve(transport: str, *, host: str = "127.0.0.1", port: int = 8765) -> int:
    server.ensure_backup_db_current()

    kwargs = {}
    if transport != "stdio":
        kwargs = {"host": host, "port": port}

    server.mcp.run(transport=transport, **kwargs)
    return 0


def _doctor() -> int:
    print("2do-mcp doctor")
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
