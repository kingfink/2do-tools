# 2Do MCP Server

An MCP server for reading tasks from 2Do.

This server is macOS-only. It reads from the local 2Do macOS app database and
uses macOS application support and group-container paths.

This project is experimental and provided as-is, without warranty, support, or
liability for data loss, service interruption, or other issues.

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

## Install

You need [`uv`](https://docs.astral.sh/uv/) (a single self-contained binary):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: brew install uv
```

Then add this MCP server to your client. The same command works everywhere — no clone, no virtualenv, no PATH setup. `uv` fetches and caches the server from GitHub on first run.

```json
{
  "mcpServers": {
    "2do": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/kingfink/2do-mcp@v0.1.0",
        "2do-mcp",
        "serve"
      ]
    }
  }
}
```

| Client | Where the config goes |
| --- | --- |
| Claude Code | The project's `.mcp.json` (already configured in this repo), or run `claude mcp add-json 2do '{"type":"stdio","command":"uvx","args":["--from","git+https://github.com/kingfink/2do-mcp@v0.1.0","2do-mcp","serve"]}'`. |
| Codex | `codex mcp add 2do -- uvx --from git+https://github.com/kingfink/2do-mcp@v0.1.0 2do-mcp serve` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude Desktop. |

Upgrade later by bumping the `@v0.1.0` tag to a newer release.

Check your setup:

```bash
uvx --from git+https://github.com/kingfink/2do-mcp@v0.1.0 2do-mcp doctor
```

If the server cannot find the 2Do database, make sure 2Do has been opened at least once and that the client running this server has permission to read `~/Library/Group Containers`.

## Advanced

### Claude Desktop one-click bundle (MCPB)

Claude Desktop can install a `.mcpb` bundle from Settings > Extensions > Advanced settings > Install Extension. The bundle still launches the server via `uvx`, so `uv` must be installed.

Build it with:

```bash
npm install -g @anthropic-ai/mcpb
scripts/build-mcpb.sh
```

The script writes `dist/2do-mcp.mcpb`. Install the bundle by double-clicking it, dragging it into Claude Desktop, or using the Extensions settings.

### Plugin marketplaces

This repo doubles as a plugin marketplace for Claude Code and Codex. The plugin definition lives under `plugins/2do/`.

Claude Code:

```bash
claude plugin marketplace add https://github.com/kingfink/2do-mcp
claude plugin install 2do@2do-mcp
```

Codex:

```bash
codex plugin marketplace add https://github.com/kingfink/2do-mcp
```

Then install the `2do` plugin from the Codex plugin UI.

### Remote connectors (Claude Cowork, ChatGPT)

Cowork and ChatGPT reach MCP servers from the cloud, so a local stdio server is not enough — you must expose a Streamable HTTP endpoint over HTTPS.

Run the server with HTTP transport:

```bash
uvx --from git+https://github.com/kingfink/2do-mcp@v0.1.0 2do-mcp \
  serve --transport streamable-http --host 127.0.0.1 --port 8765
```

The local endpoint is `http://127.0.0.1:8765/mcp`. Expose it through a trusted HTTPS tunnel or hosted deployment, then add the public URL as a custom connector (Claude) or a custom MCP app in developer mode (ChatGPT). Do not share a tunneled 2Do endpoint unless you are comfortable exposing your local task data.

For copy-paste setup guidance from the CLI:

```bash
uvx --from git+https://github.com/kingfink/2do-mcp@v0.1.0 2do-mcp connect claude-cowork
uvx --from git+https://github.com/kingfink/2do-mcp@v0.1.0 2do-mcp connect chatgpt
```

- Claude custom connectors: <https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>
- ChatGPT MCP apps: <https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt>

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

Clone the repo and create a dev environment with `uv`:

```bash
uv sync --extra dev
```

Run the server from your checkout:

```bash
uv run 2do-mcp serve
```

Run checks:

```bash
git ls-files '*.py' -z | xargs -0 python3 -m py_compile
uv run ruff check .
uv run ruff format --check .
```

## TODOs

- [ ] Add richer task tools and filters:
  - [ ] list calendars
  - [ ] list tags
  - [ ] get overdue tasks
  - [ ] get tasks due today
  - [ ] get upcoming tasks
  - [ ] search or filter tasks by list, tag, due range, and completion state
- [ ] Add tests for timestamp sentinel handling, tag parsing, SQL filter construction, schema validation, and backup promotion.
