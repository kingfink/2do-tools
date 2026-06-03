# 2Do Tools

An MCP server for reading tasks from 2Do.

This server is macOS-only. It reads from the local 2Do macOS app database and
uses macOS application support and group-container paths.

This project is experimental and provided as-is, without warranty, support, or
liability for data loss, service interruption, or other issues.

This project is independent and is not affiliated with, endorsed by, or
supported by the 2Do app or its developer. It uses the 2Do name only to describe
compatibility.

The server keeps its own local backup of 2Do's SQLite database under
`~/Library/Application Support/2do-tools/backups/` and serves read-only task
queries from that copy. It does not write to the original 2Do database.

## Tools

- `list_lists`: list 2Do lists.
- `list_tags`: list non-deleted 2Do tags.
- `list_tasks`: search and filter tasks by list, tag, due date range,
  completion date range, completion state, and query text.
- `list_tasks_overdue`: list open tasks due before today.
- `list_tasks_inbox`: list open tasks in the Inbox list.
- `list_tasks_due_today`: list open tasks due today.
- `list_tasks_due_this_week`: list open tasks due during the current calendar
  week.
- `list_tasks_completed_today`: list tasks completed today.
- `list_tasks_completed_this_week`: list tasks completed during the current
  calendar week.
- `open_task`: open a 2Do task by UID using 2Do's macOS URL scheme.
- `open_list`: open a 2Do list by name using 2Do's macOS URL scheme.
- `open_search`: open a search in 2Do using 2Do's macOS URL scheme.
- `refresh_backup_db`: find the local 2Do database again, copy it into
  the app support backup directory, validate it, and replace the previous
  backup.

Task and list results include a `url` field with the matching `twodo://`
navigation URL, so clients can render links directly even when they do not call
the `open_*` tools.

## Install

You need [`uv`](https://docs.astral.sh/uv/) (a single self-contained binary):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: brew install uv
```

Then add the server to your client. Each client has a one-step install:

| Client | Simplest install |
| --- | --- |
| Claude Code | `claude plugin marketplace add kingfink/2do-tools` then `claude plugin install 2do@2do-tools` |
| Codex | `codex mcp add 2do -- uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do mcp serve` |
| Claude Desktop | Download `2do-tools.mcpb` from the [latest release](https://github.com/kingfink/2do-tools/releases/latest) and double-click it |

Every route runs the same thing under the hood — `uv` fetches and caches the server from GitHub on first run. No clone, no virtualenv, no PATH setup.

> These routes require the `v0.6.0` release or newer.

For any other client, or to configure it by hand, use this config:

```json
{
  "mcpServers": {
    "2do": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/kingfink/2do-tools@v0.6.0",
        "2do",
        "mcp",
        "serve"
      ]
    }
  }
}
```

### Updating

Use the newest tag from the [latest release](https://github.com/kingfink/2do-tools/releases/latest)
when updating.

For the standalone CLI installed with `uv tool install`, reinstall with the new
tag:

```bash
uv tool install --force "git+https://github.com/kingfink/2do-tools@v0.6.0"
```

For Codex, replace the MCP entry with the new tag:

```bash
codex mcp remove 2do
codex mcp add 2do -- uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do mcp serve
```

For manual MCP JSON configs, change the `@v0.6.0` tag in the `uvx --from`
argument and restart the client. For Claude Code plugins, run
`claude plugin update 2do` and restart Claude Code. For Claude Desktop, download
the latest `2do-tools.mcpb` release asset and install it over the existing
extension.

Check your setup:

```bash
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do doctor
```

If the server cannot find the 2Do database, make sure 2Do has been opened at least once and that the client running this server has permission to read `~/Library/Group Containers`.

## CLI

Install the CLI as a standalone command with `uv`:

```bash
uv tool install "git+https://github.com/kingfink/2do-tools@v0.6.0"
uv tool update-shell
```

For local development from a checkout, install the editable package:

```bash
uv tool install --editable .
uv tool update-shell
```

Open a new terminal after `uv tool update-shell`, or run
`export PATH="$(uv tool dir --bin):$PATH"` in the current shell. Older releases
installed the previous `2do-mcp` command name.

Verify the CLI:

```bash
2do --help
2do doctor
```

Then use it for quick task lookups:

```bash
2do task list
2do task list --query invoice --list Projects
2do task list --has-due-date --json
2do task open task-uid
2do list list
2do list open Inbox
2do tag list
2do search open invoice
```

`2do task list` lists open tasks by default. Use `--all` to include completed tasks,
or `--completed` to show only completed tasks. Task filters include `--list`,
`--list-id`, `--tag`, `--tag-id`, `--due-from`, `--due-before`,
`--completed-from`, `--completed-before`, `--has-due-date`, `--query`, and
`--limit`.

## Agent Skills

Codex and Claude plugin installs include three skills:

- 2Do Daily Review: review overdue, due today, upcoming, inbox, and recently
  completed tasks.
- 2Do Task Lookup: find, filter, list, or open tasks, lists, tags, and searches.
- 2Do Setup Diagnostics: troubleshoot CLI, MCP, plugin, permission, and database
  discovery issues.

In Claude, plugin skills are available in Claude chat, Claude Desktop's Chat tab,
and Claude Cowork after the plugin is installed. Connector-only installs, such as
ChatGPT custom MCP apps, Claude remote connectors, and Claude Desktop MCPB
extensions, do not install skills from this repo; they use the MCP tools and
server instructions. The same prompts still work, such as "review my 2Do tasks
for today", "find 2Do tasks tagged Work with a due date", or "diagnose my 2Do
setup".

## Advanced

### Claude Desktop bundle (MCPB)

The simplest path is to download the prebuilt `2do-tools.mcpb` from the [latest release](https://github.com/kingfink/2do-tools/releases/latest) and double-click it (or drag it into Settings > Extensions > Advanced settings > Install Extension). The bundle launches the server via `uvx`, so `uv` must be installed.

To build the bundle yourself from a checkout:

```bash
npm install -g @anthropic-ai/mcpb
scripts/build-mcpb.sh
```

The script writes `dist/2do-tools.mcpb`.

### Claude Code plugin marketplace

This repo doubles as a Claude Code plugin marketplace. The plugin definition lives under `plugins/2do/`.

```bash
claude plugin marketplace add kingfink/2do-tools
claude plugin install 2do@2do-tools
```

For Codex, use the `codex mcp add` command from the Install table above — Codex installs MCP servers directly rather than from a plugin marketplace.

### Remote connectors (Claude Cowork, ChatGPT)

> Advanced, private use only. Prefer the local stdio, plugin, or MCPB install
> paths unless you specifically need a cloud-hosted client to reach this server.

Cowork and ChatGPT reach MCP servers from the cloud, so a local stdio server is
not enough. The Streamable HTTP transport in this project does not add its own
authentication layer. If you expose it, put it behind HTTPS and authentication
that restricts access to trusted users only. A secret or hard-to-guess tunnel URL
is not authentication.

Do not expose this endpoint publicly. Anyone who can reach the authenticated MCP
endpoint can query the local 2Do task backup served by this Mac. They may also
be able to call URL scheme navigation tools that bring 2Do to the front or open
task, list, or search views on the host Mac.

Run the server with HTTP transport:

```bash
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do \
  mcp serve --transport streamable-http --host 127.0.0.1 --port 8765
```

The local endpoint is `http://127.0.0.1:8765/mcp`. Expose it only through a
trusted HTTPS tunnel, reverse proxy, or private deployment that enforces
authentication before traffic reaches the MCP server.

For copy-paste setup guidance from the CLI:

```bash
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do mcp connect claude-cowork
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do mcp connect chatgpt
```

- Claude custom connectors: <https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>
- ChatGPT MCP apps: <https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt>

## Backup Behavior

On startup, the server checks for
`~/Library/Application Support/2do-tools/backups/2do.db`. If that backup does not
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

Task tools also check whether at least five minutes have elapsed since
the last automatic refresh check before opening the read-only backup.

If a previous refresh recorded the source database path and the source `2do.db*`
files are not newer than the matching local backup files, refresh skips copying.
Otherwise, refreshes follow this flow:

1. Copy each candidate database and its related SQLite sidecar files, such as
   `2do.db-wal` and `2do.db-shm`, into a temporary
   `~/Library/Application Support/2do-tools/backups/.incoming-*` directory.
2. Validate the copied database with SQLite `PRAGMA integrity_check`.
3. Confirm the expected task, list, and tag storage exists.
4. Confirm every column used by task, list, and tag queries exists.
5. Promote exactly one valid staged copy into the app support backup directory.

If no valid database is found, or if multiple valid 2Do databases are found, the
refresh fails instead of guessing.

## Privacy

The backup is stored locally under
`~/Library/Application Support/2do-tools/backups/`. It may contain task titles,
notes, list names, tags, timestamps, and other 2Do data.

The URL scheme navigation tools launch `twodo://` URLs on the Mac running the
MCP server. If you expose the server through a remote connector, remote clients
that can call these tools can also bring 2Do to the front or open task/list/search
views on that Mac.

## License

This project is available under the MIT License. See [LICENSE](LICENSE).

## Development

Clone the repo and create a dev environment with `uv`:

```bash
uv sync --extra dev
```

Run the server from your checkout:

```bash
uv run 2do mcp serve
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

Prepare the release PR from GitHub Actions:

1. Open Actions > Prepare Release PR > Run workflow.
2. Enter the tag, such as `v0.6.0`.
3. Merge the generated PR after CI passes.

The workflow needs permission to create pull requests. Enable Settings > Actions
> General > Workflow permissions > Allow GitHub Actions to create and approve
pull requests. If a run pushes the release branch but cannot open the PR, fix
the permission and rerun the workflow with the same tag.

To prepare the same PR locally instead, run this from a clean checkout:

```bash
scripts/prepare-release.sh v0.6.0
```

`scripts/prepare-release.sh` checks out `master`, pulls the latest `origin/master`,
creates `codex/release-v0.6.0`, updates the version references in
`pyproject.toml`, `mcpb/manifest.json`, `mcpb/server.py`, and this README, runs
the standard checks, commits the version bump, pushes the release branch, and
opens the PR. The version update and validation logic lives in
`scripts/release_metadata.py` so local preparation and CI use the same metadata
checks.

After the PR merges, publish the release from GitHub Actions:

1. Open Actions > Release > Run workflow.
2. Enter the same tag, such as `v0.6.0`.
3. Run the workflow from `master`.

The workflow installs `mcpb`, verifies that the checked-out `master` version
metadata matches the tag, and runs `scripts/release.sh`. The release script
validates and packs `dist/2do-tools.mcpb`, creates the GitHub release, uploads the
bundle asset, and creates the remote tag at the current `master` commit.

## TODOs

- [x] Incorporate URL scheme navigation functionality as documented
  [here](https://www.2doapp.com/docs/macos/url-schemes/)
  - [x] Keep backup DB / SQLite functionality as the read/query source. URL
    schemes are for navigation and user automation, not structured reads.
  - [x] Add `url_schemes.py` helpers for `showtask`, `showlist`, and `search`.
  - [x] Enrich task and list results with `twodo://` navigation URLs.
  - [x] Add `open_task`, `open_list`, and `open_search` navigation tools.
- [ ] Add safe task creation via URL schemes:
  - [ ] `addnewtask` to open the interface to add a new task instead of
    creating the task or prepopulating info. Documentation
    [here](https://www.2doapp.com/docs/macos/url-schemes/#creating-tasks-with-add)
  - [ ] `add?usequickentry=1` to open Quick Entry prepopulated with `task`
    (title, required), `note` (optional), `forlist` (optional), `type=0`,
    `due` (optional), `repeat` (optional), and `tags` (optional).
- [ ] Add direct task creation via URL schemes:
  - [ ] `add` a regular task directly with explicit confirmation/callback
    handling and the same constrained task fields above.
  - [ ] Capture the new task UID from `x-success` callback data where possible.
- [ ] Add single-task completion via URL schemes:
  - [ ] `completetasks` for exactly one UID, with confirmation/callback
    handling. Documentation
    [here](https://www.2doapp.com/docs/macos/url-schemes/#completing-tasks-by-uid)
- [ ] Extend this as a more general CLI using the URL schemes
- [x] Extend to have skills/plugins/whatever to leverage the CLI
