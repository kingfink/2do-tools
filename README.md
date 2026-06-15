# 2Do Tools

A local MCP server and CLI for reading, creating, and completing tasks in the [2Do macOS app](https://www.2doapp.com/macos/).

2Do Tools lets AI clients and terminal workflows query your local 2Do tasks, inspect lists and tags, open matching views in 2Do, create and complete tasks safely, and refresh a local backup of the 2Do database. It is macOS-only.

The server reads from its own backup under `~/Library/Application Support/2do-tools/backups/`. Database access remains read-only. Task creation is delegated to 2Do through its documented URL scheme, rather than writing to the original 2Do database.

This project is experimental, provided as-is, and independent from 2Do and its developer. It uses the 2Do name only to describe compatibility.

## Install

Install [`uv`](https://docs.astral.sh/uv/) first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: brew install uv
```

Then add 2Do Tools to your client:

| Client | Simplest install |
| --- | --- |
| Claude Code | `claude plugin marketplace add kingfink/2do-tools` then `claude plugin install 2do@2do-tools` |
| Codex | `codex mcp add 2do -- uvx --refresh-package 2do-tools --from git+https://github.com/kingfink/2do-tools@stable 2do mcp serve` |
| Claude Desktop | Download `2do-tools.mcpb` from the [latest release](https://github.com/kingfink/2do-tools/releases/latest) and double-click it |

New Claude Code plugin, Claude Desktop MCPB, Codex, and other MCP installs use
the `stable` Git ref. Their `uvx` command refreshes `2do-tools` before resolving
that ref, so no clone, virtualenv, or PATH setup is required. Fully quit and
reopen the client to restart its MCP server and revalidate `stable`.

For other MCP clients, use this config:

```json
{
  "mcpServers": {
    "2do": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--refresh-package",
        "2do-tools",
        "--from",
        "git+https://github.com/kingfink/2do-tools@stable",
        "2do",
        "mcp",
        "serve"
      ]
    }
  }
}
```

Check the setup:

```bash
uvx --refresh-package 2do-tools --from git+https://github.com/kingfink/2do-tools@stable 2do doctor
```

### Migrate Existing Installs

Existing installations pinned to a version tag do not switch automatically.
Migrate each existing install once:

- Claude Code plugin: refresh the marketplace entry, reinstall the plugin, then
  restart Claude Code:

  ```bash
  claude plugin marketplace update 2do-tools
  claude plugin uninstall 2do@2do-tools
  claude plugin install 2do@2do-tools
  ```

  The reinstalled plugin ships the stable MCP config, so future server updates
  resolve through `stable` without another plugin version update.
- Codex: remove and re-add the server with `stable`, then fully quit and reopen
  Codex:

  ```bash
  codex mcp remove 2do
  codex mcp add 2do -- uvx --refresh-package 2do-tools --from git+https://github.com/kingfink/2do-tools@stable 2do mcp serve
  ```

- Other MCP clients: replace `@vX.Y.Z` with `@stable`, add
  `--refresh-package`, `2do-tools` before `--from`, then restart the client.
- Claude Desktop: install the newest MCPB once. Subsequent launches resolve
  `stable`; fully quit and reopen Claude Desktop to restart the server.
- Standalone CLI: run the one-time force install shown below.

## CLI

Install the CLI as a standalone command:

```bash
uv tool install "git+https://github.com/kingfink/2do-tools@stable"
uv tool update-shell
```

Migrate an existing version-tagged CLI installation once:

```bash
uv tool install --force "git+https://github.com/kingfink/2do-tools@stable"
```

For normal CLI updates after migration:

```bash
uv tool upgrade 2do-tools
2do doctor
```

The CLI is a persistent tool installation, so restarting a terminal or MCP
client does not update it. Run `uv tool upgrade 2do-tools` explicitly.

Open a new terminal after `uv tool update-shell`, then try:

```bash
2do doctor
2do task list
2do task list --query invoice --list Projects
2do task list --due-today
2do task list --overdue --recurring
2do task list --has-due-date --json
2do task open task-uid
2do task quick-entry "Buy milk" --list Inbox --tag Home
2do task create "Submit report" --due 2026-06-20 --repeat weekly
2do task complete task-uid
2do list list
2do tag list
2do search open invoice
```

Run `2do task list --help` for all filters.

## Capabilities

- Search and filter tasks by list, tag, due date, completion date, completion state, and query text.
- Use shortcuts for common date groups such as overdue, due today, due this week, completed today, and completed this week.
- List 2Do lists and tags.
- Open tasks, lists, and searches in 2Do using `twodo://` URL schemes.
- Open a pre-filled Quick Entry editor for review and saving in 2Do.
- Create tasks directly after explicit confirmation. MCP uses client elicitation when available and otherwise confirms on the host Mac; the CLI uses a terminal prompt.
- Complete exactly one existing task after the same explicit confirmation.
- Refresh the local read-only database backup.

Task creation supports a required title plus optional notes, list, due date, tags, and daily, weekly, biweekly, or monthly repeat presets. Repeating tasks require a due date.

Codex and Claude plugin installs also include skills for daily review, task lookup, and setup diagnostics. Connector-only installs, such as ChatGPT custom MCP apps, Claude remote connectors, and Claude Desktop MCPB extensions, expose the MCP tools but do not install repo skills.

## Privacy And Local Data

The local backup may contain task titles, notes, list names, tags, timestamps, and other 2Do data. Do not share database files, task exports, screenshots with private tasks, credentials, or tunnel URLs.

The `open_*` tools launch `twodo://` URLs on the Mac running the MCP server. If you expose the server through a remote connector, remote clients that can call those tools can also bring 2Do to the front or open task/list/search views on that Mac. Quick Entry opens an editor on that Mac. Direct task creation and completion always require either MCP elicitation or a native confirmation dialog on that Mac.

Direct mutation callbacks use a generated background URL handler under `~/Library/Application Support/2do-tools/` so 2Do can report success, errors, or cancellation without opening a browser tab.

## Remote Connectors

Remote connectors for Claude Cowork or ChatGPT are advanced private setups. A cloud-hosted client cannot reach a local stdio server directly, so you must run the Streamable HTTP transport and expose it through HTTPS plus real authentication. A secret or hard-to-guess tunnel URL is not authentication.

```bash
uvx --refresh-package 2do-tools --from git+https://github.com/kingfink/2do-tools@stable 2do mcp serve --transport streamable-http --host 127.0.0.1 --port 8765
```

The local endpoint is `http://127.0.0.1:8765/mcp`. For copy-paste setup guidance:

```bash
uvx --refresh-package 2do-tools --from git+https://github.com/kingfink/2do-tools@stable 2do mcp connect claude-cowork
uvx --refresh-package 2do-tools --from git+https://github.com/kingfink/2do-tools@stable 2do mcp connect chatgpt
```

Related docs:

- Claude custom connectors: <https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>
- ChatGPT MCP apps: <https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt>

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for local development, release, and maintainer notes.

## License

This project is available under the MIT License. See [LICENSE](LICENSE).
