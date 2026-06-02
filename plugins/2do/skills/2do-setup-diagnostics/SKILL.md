---
name: 2do-setup-diagnostics
description: Use when troubleshooting 2Do Tools, the `2do` CLI, MCP server, plugin install, database discovery, permissions, stale tasks, or remote connector setup.
---

# 2Do Setup Diagnostics

Start with the smallest useful checks:

1. Run `2do doctor`.
2. If the command is missing, run `which 2do` and `2do --help`.
3. If tasks are stale or missing, run `2do refresh`, then `2do task list --json --limit 5`.
4. For MCP startup, run `2do mcp serve --help`.
5. For remote connectors, use `2do mcp serve --transport streamable-http --host 127.0.0.1 --port 8765`, then `2do mcp connect chatgpt` or `2do mcp connect claude-cowork`.

Report the exact failing command and relevant output. Mention macOS app data or permissions only when `doctor` or file access points there. Do not suggest destructive cleanup.
