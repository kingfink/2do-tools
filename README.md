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

- `list_lists`: list 2Do lists.
- `list_tags`: list non-deleted 2Do tags.
- `get_tasks`: search and filter tasks by list, tag, due date range,
  completion date range, completion state, and query text.
- `get_overdue_tasks`: list open tasks due before today.
- `get_inbox_tasks`: list open tasks in the Inbox list.
- `get_tasks_due_today`: list open tasks due today.
- `get_tasks_due_this_week`: list open tasks due during the current calendar
  week.
- `get_tasks_completed_today`: list tasks completed today.
- `get_tasks_completed_this_week`: list tasks completed during the current
  calendar week.
- `get_open_tasks`: compatibility shortcut for open, non-deleted,
  non-archived tasks.
- `count_open_tasks`: count open, non-deleted, non-archived tasks.
- `get_completed_tasks`: compatibility shortcut for completed, non-deleted,
  non-archived tasks.
- `count_completed_tasks`: count completed, non-deleted, non-archived tasks.
- `refresh_backup_db`: find the local 2Do database again, copy it into
  the app support backup directory, validate it, and replace the previous
  backup.

## Install

You need [`uv`](https://docs.astral.sh/uv/) (a single self-contained binary):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: brew install uv
```

Then add the server to your client. Each client has a one-step install:

| Client | Simplest install |
| --- | --- |
| Claude Code | `claude plugin marketplace add kingfink/2do-mcp` then `claude plugin install 2do@2do-mcp` |
| Codex | `codex mcp add 2do -- uvx --from git+https://github.com/kingfink/2do-mcp@v0.2.0 2do-mcp serve` |
| Claude Desktop | Download `2do-mcp.mcpb` from the [latest release](https://github.com/kingfink/2do-mcp/releases/latest) and double-click it |

Every route runs the same thing under the hood — `uv` fetches and caches the server from GitHub on first run. No clone, no virtualenv, no PATH setup.

> These routes require the `v0.2.0` release. Until it is published, install by hand with the config below.

For any other client, or to configure it by hand, use this config:

```json
{
  "mcpServers": {
    "2do": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/kingfink/2do-mcp@v0.2.0",
        "2do-mcp",
        "serve"
      ]
    }
  }
}
```

Upgrade later by bumping the `@v0.2.0` tag to a newer release.

Check your setup:

```bash
uvx --from git+https://github.com/kingfink/2do-mcp@v0.2.0 2do-mcp doctor
```

If the server cannot find the 2Do database, make sure 2Do has been opened at least once and that the client running this server has permission to read `~/Library/Group Containers`.

## Advanced

### Claude Desktop bundle (MCPB)

The simplest path is to download the prebuilt `2do-mcp.mcpb` from the [latest release](https://github.com/kingfink/2do-mcp/releases/latest) and double-click it (or drag it into Settings > Extensions > Advanced settings > Install Extension). The bundle launches the server via `uvx`, so `uv` must be installed.

To build the bundle yourself from a checkout:

```bash
npm install -g @anthropic-ai/mcpb
scripts/build-mcpb.sh
```

The script writes `dist/2do-mcp.mcpb`.

### Claude Code plugin marketplace

This repo doubles as a Claude Code plugin marketplace. The plugin definition lives under `plugins/2do/`.

```bash
claude plugin marketplace add kingfink/2do-mcp
claude plugin install 2do@2do-mcp
```

For Codex, use the `codex mcp add` command from the Install table above — Codex installs MCP servers directly rather than from a plugin marketplace.

### Remote connectors (Claude Cowork, ChatGPT)

Cowork and ChatGPT reach MCP servers from the cloud, so a local stdio server is not enough — you must expose a Streamable HTTP endpoint over HTTPS.

Run the server with HTTP transport:

```bash
uvx --from git+https://github.com/kingfink/2do-mcp@v0.2.0 2do-mcp \
  serve --transport streamable-http --host 127.0.0.1 --port 8765
```

The local endpoint is `http://127.0.0.1:8765/mcp`. Expose it through a trusted HTTPS tunnel or hosted deployment, then add the public URL as a custom connector (Claude) or a custom MCP app in developer mode (ChatGPT). Do not share a tunneled 2Do endpoint unless you are comfortable exposing your local task data.

For copy-paste setup guidance from the CLI:

```bash
uvx --from git+https://github.com/kingfink/2do-mcp@v0.2.0 2do-mcp connect claude-cowork
uvx --from git+https://github.com/kingfink/2do-mcp@v0.2.0 2do-mcp connect chatgpt
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
3. Confirm the expected task, list, and tag storage exists.
4. Confirm every column used by task, list, and tag queries exists.
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
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

## Release

Releases use a two-step flow: prepare a normal version-bump PR, then publish
the GitHub release from CI after that PR merges.

Prepare the release PR from a clean checkout:

```bash
git checkout master
git pull --ff-only origin master
git checkout -b codex/release-v0.3.0
scripts/prepare-release.sh v0.3.0
git push -u origin codex/release-v0.3.0
gh pr create --base master --head codex/release-v0.3.0 --title "Bump version to v0.3.0"
```

`scripts/prepare-release.sh` updates the version references in `pyproject.toml`,
`mcpb/manifest.json`, `mcpb/server.py`, and this README, runs the standard
checks, and commits the version bump. The version update and validation logic
lives in `scripts/release_metadata.py` so local preparation and CI use the same
metadata checks.

After the PR merges, publish the release from GitHub Actions:

1. Open Actions > Release > Run workflow.
2. Enter the same tag, such as `v0.3.0`.
3. Run the workflow from `master`.

The workflow installs `mcpb`, verifies that the checked-out `master` version
metadata matches the tag, and runs `scripts/release.sh`. The release script
validates and packs `dist/2do-mcp.mcpb`, creates the GitHub release, uploads the
bundle asset, and creates the remote tag at the current `master` commit.

## TODOs

- [ ] Add the ability to add a new task (through the email relay to keep things read only)
- [ ] Add tests for timestamp sentinel handling, tag parsing, SQL filter construction, schema validation, and backup promotion.
