# 2Do Tools

A local, read-only MCP server and CLI for the 2Do macOS app.

2Do Tools lets AI clients and terminal workflows query your local 2Do tasks,
inspect lists and tags, open matching views in 2Do, and refresh a local backup
of the 2Do database. It is macOS-only.

The server reads from its own backup under
`~/Library/Application Support/2do-tools/backups/` and does not write to the
original 2Do database.

This project is experimental, provided as-is, and independent from 2Do and its
developer. It uses the 2Do name only to describe compatibility.

## Install

Install [`uv`](https://docs.astral.sh/uv/) first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: brew install uv
```

Then add 2Do Tools to your client:

| Client | Simplest install |
| --- | --- |
| Claude Code | `claude plugin marketplace add kingfink/2do-tools` then `claude plugin install 2do@2do-tools` |
| Codex | `codex mcp add 2do -- uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do mcp serve` |
| Claude Desktop | Download `2do-tools.mcpb` from the [latest release](https://github.com/kingfink/2do-tools/releases/latest) and double-click it |

All install paths run the same pinned `uvx` command under the hood, so no clone,
virtualenv, or PATH setup is required. These install routes require `v0.6.0` or
newer.

For other MCP clients, use this config:

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

Check the setup:

```bash
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do doctor
```

When updating, use the newest tag from the
[latest release](https://github.com/kingfink/2do-tools/releases/latest). Update
the pinned tag in your MCP config, run `claude plugin update 2do` for Claude
Code plugin installs, or reinstall the latest Claude Desktop MCPB asset.

## CLI

Install the CLI as a standalone command:

```bash
uv tool install "git+https://github.com/kingfink/2do-tools@v0.6.0"
uv tool update-shell
```

Open a new terminal after `uv tool update-shell`, then try:

```bash
2do doctor
2do task list
2do task list --query invoice --list Projects
2do task list --has-due-date --json
2do task open task-uid
2do list list
2do tag list
2do search open invoice
```

Run `2do task list --help` for all filters.

## Capabilities

- Search and filter tasks by list, tag, due date, completion date, completion
  state, and query text.
- Use shortcuts for common date groups such as overdue, due today, due this
  week, completed today, and completed this week.
- List 2Do lists and tags.
- Open tasks, lists, and searches in 2Do using `twodo://` URL schemes.
- Refresh the local read-only database backup.

Codex and Claude plugin installs also include skills for daily review, task
lookup, and setup diagnostics. Connector-only installs, such as ChatGPT custom
MCP apps, Claude remote connectors, and Claude Desktop MCPB extensions, expose
the MCP tools but do not install repo skills.

## Privacy And Local Data

The local backup may contain task titles, notes, list names, tags, timestamps,
and other 2Do data. Do not share database files, task exports, screenshots with
private tasks, credentials, or tunnel URLs.

The `open_*` tools launch `twodo://` URLs on the Mac running the MCP server. If
you expose the server through a remote connector, remote clients that can call
those tools can also bring 2Do to the front or open task/list/search views on
that Mac.

## Remote Connectors

Remote connectors for Claude Cowork or ChatGPT are advanced private setups. A
cloud-hosted client cannot reach a local stdio server directly, so you must run
the Streamable HTTP transport and expose it through HTTPS plus real
authentication. A secret or hard-to-guess tunnel URL is not authentication.

```bash
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do \
  mcp serve --transport streamable-http --host 127.0.0.1 --port 8765
```

The local endpoint is `http://127.0.0.1:8765/mcp`. For copy-paste setup
guidance:

```bash
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do mcp connect claude-cowork
uvx --from git+https://github.com/kingfink/2do-tools@v0.6.0 2do mcp connect chatgpt
```

Related docs:

- Claude custom connectors: <https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>
- ChatGPT MCP apps: <https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt>

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for local development, release, and
maintainer notes.

## License

This project is available under the MIT License. See [LICENSE](LICENSE).
