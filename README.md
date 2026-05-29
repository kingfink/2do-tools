# 2Do MCP Server

An MCP server for reading tasks from 2Do.

The server keeps its own local backup of 2Do's SQLite database under
`~/Library/Application Support/2do-mcp/backups/` and serves read-only task
queries from that copy. It does not write to the original 2Do database.

## Tools

- `get_open_tasks`: list open, non-deleted, non-archived tasks.
- `count_open_tasks`: count open, non-deleted, non-archived tasks.
- `get_completed_tasks`: list completed, non-deleted, non-archived tasks.
- `count_completed_tasks`: count completed, non-deleted, non-archived tasks.
- `refresh_backup_db`: find the local 2Do database again, copy it into
  the app support backup directory, validate it, and replace the previous
  backup.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -e '.[dev]'
```

Check setup:

```bash
venv/bin/2do-mcp doctor
```

Run the MCP server:

```bash
venv/bin/2do-mcp serve
```

Refresh the backup:

```bash
venv/bin/2do-mcp refresh
```

If the server cannot find the 2Do database, make sure 2Do has been opened at
least once and that the app or terminal running this server has permission to
read `~/Library/Group Containers`.

## MCP Client Configuration

Use `2do-mcp` as the MCP command. For example:

```json
{
  "mcpServers": {
    "2do": {
      "type": "stdio",
      "command": "2do-mcp",
      "args": ["serve"]
    }
  }
}
```

Make sure `2do-mcp` is on the `PATH` seen by the MCP client. For local
development, use the absolute path to `venv/bin/2do-mcp` if the client does not
inherit your shell environment.

## Backup Behavior

On startup, the server checks for
`~/Library/Application Support/2do-mcp/backups/2do.db`. If that backup does not
exist, it searches for candidate `2do.db` files in this order:

1. 2Do's known app-group container:
   `~/Library/Group Containers/EKT6323JY3.com.guidedways/2do.db`.
2. Any group-container path named by the installed `2Do.app` bundle's
   `BeehiveSharedDefaultsKey` value.

These checks match how sandboxed macOS apps commonly store shared data: the
leading `EKT6323JY3` value is 2Do's Apple Developer Team ID, and the full
directory name is the app group shared by 2Do and its helpers/extensions. The
`BeehiveSharedDefaultsKey` value is a 2Do-specific app-bundle clue, not a
general macOS standard.

Task and count tools also check whether at least five minutes have elapsed since
the last automatic refresh check before opening the read-only backup.

If a previous refresh recorded the source database path and the source `2do.db*`
files are not newer than the matching local backup files, refresh skips copying.
Otherwise, refreshes follow this flow:

1. Copy each candidate database and its related SQLite sidecar files, such as
   `2do.db-wal` and `2do.db-shm`, into a temporary
   `~/Library/Application Support/2do-mcp/backups/.incoming-*` directory.
2. Validate the copied database with SQLite `PRAGMA integrity_check`.
3. Confirm the expected `tasks`, `calendars`, and `tags` tables exist.
4. Confirm every column used by task, calendar, and tag queries exists.
5. Promote exactly one valid staged copy into the app support backup directory.

If no valid database is found, or if multiple valid 2Do databases are found, the
refresh fails instead of guessing.

## Privacy

The backup is stored locally under
`~/Library/Application Support/2do-mcp/backups/`. It may contain task titles,
notes, list names, tags, timestamps, and other 2Do data.

## Development

Run checks with:

```bash
git ls-files '*.py' -z | xargs -0 python3 -m py_compile
venv/bin/python -m ruff check .
venv/bin/python -m ruff format --check .
```

## TODOs

- [x] Validate every SQLite column used by task, calendar, and tag queries before accepting a backup.
- [x] Make tag filtering delimiter-aware instead of using substring `LIKE` matching.
- [ ] Add richer task tools and filters:
  - [ ] list calendars
  - [ ] list tags
  - [ ] get overdue tasks
  - [ ] get tasks due today
  - [ ] get upcoming tasks
  - [ ] search or filter tasks by list, tag, due range, and completion state
- [ ] Add tests for timestamp sentinel handling, tag parsing, SQL filter construction, schema validation, and backup promotion.
