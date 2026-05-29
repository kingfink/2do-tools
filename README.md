# 2Do MCP Server

An MCP server for reading tasks from 2Do.

The server keeps its own local backup of 2Do's SQLite database under `backups/`
and serves read-only task queries from that copy. It does not write to the
original 2Do database.

## Tools

- `get_open_tasks`: list open, non-deleted, non-archived tasks.
- `count_open_tasks`: count open, non-deleted, non-archived tasks.
- `get_completed_tasks`: list completed, non-deleted, non-archived tasks.
- `count_completed_tasks`: count completed, non-deleted, non-archived tasks.
- `refresh_backup_db`: find the local 2Do database again, copy it into
  `backups/`, validate it, and replace the previous backup.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Run the server directly:

```bash
./run-server.sh
```

If the server cannot find the 2Do database, make sure 2Do has been opened at
least once and that the app or terminal running this server has permission to
read `~/Library/Group Containers`.

## MCP Client Configuration

Use `run-server.sh` as the MCP command. For example:

```json
{
  "mcpServers": {
    "2do": {
      "command": "/Users/tim/2do-mcp/run-server.sh"
    }
  }
}
```

Adjust the path if the repository lives somewhere else.

## Backup Behavior

On startup, the server checks for `backups/2do.db`. If that backup does not
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

Refreshes follow the same flow:

1. Copy each candidate database and its related SQLite sidecar files, such as
   `2do.db-wal` and `2do.db-shm`, into a temporary `backups/.incoming-*`
   directory.
2. Validate the copied database with SQLite `PRAGMA integrity_check`.
3. Confirm the expected `tasks`, `calendars`, and `tags` tables exist.
4. Confirm the minimum required task columns exist.
5. Promote exactly one valid staged copy into `backups/`.

If no valid database is found, or if multiple valid 2Do databases are found, the
refresh fails instead of guessing.

## Privacy

The backup is stored locally in this repository's `backups/` directory. It may
contain task titles, notes, list names, tags, timestamps, and other 2Do data.
Do not commit files from `backups/`.

## Development

Run checks with:

```bash
git ls-files '*.py' -z | xargs -0 python3 -m py_compile
venv/bin/python -m ruff check .
venv/bin/python -m ruff format --check .
```

## TODOs

- [ ] Validate every SQLite column used by task, calendar, and tag queries before accepting a backup.
- [ ] Package the server with a real entry point so MCP clients do not depend on a checked-out `venv/bin/python`.
- [ ] Add automatic backup refresh with a sensible default interval.
- [ ] Track the source database path used for the backup so refresh can compare source `2do.db*` mtimes against the local backup and skip unchanged copies.
- [ ] Make tag filtering delimiter-aware instead of using substring `LIKE` matching.
- [ ] Add richer task tools and filters:
  - [ ] list calendars
  - [ ] list tags
  - [ ] get overdue tasks
  - [ ] get tasks due today
  - [ ] get upcoming tasks
  - [ ] search or filter tasks by list, tag, due range, and completion state
- [ ] Add tests for timestamp sentinel handling, tag parsing, SQL filter construction, schema validation, and backup promotion.
