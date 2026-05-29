# uvx-based Distribution & Installation — Design

Date: 2026-05-29
Status: Approved

## Problem

Installation today is developer-grade and the README papers over it with a large
per-client matrix:

- Setup requires `git clone` → `python3 -m venv venv` →
  `pip install -e '.[dev]'` before almost any client path works.
- Committed configs use `"command": "2do-mcp"`, which only resolves after the
  venv install puts the console script on `PATH`; it silently fails otherwise.
- The README falls back to hardcoded absolute paths
  (`/Users/tim/2do-mcp/venv/bin/...`, ~6 occurrences), which are not shareable.
- There are 6+ near-duplicate plugin/marketplace scaffolds that already disagree
  with each other.

Goal: zero-friction install for anyone, GitHub-only (no PyPI for now).

## Approach

Run the server directly from GitHub with `uvx` (a.k.a. `uv tool run`). This
removes clone, venv, editable install, `PATH` dependence, and absolute paths.
`uv` is already a dependency of the existing MCPB path, so this makes the install
story more consistent, not less.

### Universal command

Every client config converges on one invocation:

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

Identical across Claude Code, Codex, and Claude Desktop. Pinned to the `v0.1.0`
tag for deterministic, cache-stable, sub-second warm starts (no per-launch
network check). Users upgrade by bumping the tag.

The only remaining user prerequisite is `uv` itself:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: brew install uv
```

## Changes

### 1. Config files → uvx command

- `.mcp.json` (root, project-scoped): `2do-mcp` command → uvx form.
- `plugins/2do/.mcp.json`: same.
- `mcpb/manifest.json`: replace the `uv run` / bundled-`src` server block with
  the uvx-from-git `mcp_config`. Bundle no longer needs `server.py`,
  `PYTHONPATH`, or a copied `src/`.
- `scripts/build-mcpb.sh`: stop copying `src/`, `pyproject.toml`, and
  `server.py`; bundle is essentially just the manifest (+ README).

### 2. De-duplicate plugin scaffolds

The repo root is a *marketplace*, not a plugin. Root plugin files are redundant
and already drifting.

- Delete `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`.
- Keep marketplace pointers `.claude-plugin/marketplace.json` and
  `.agents/plugins/marketplace.json` (both already point at `./plugins/2do`).
- Keep `plugins/2do/` as the single source of truth for the plugin definition
  (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.mcp.json`,
  `README.md`).

### 3. README restructure

- Lead with: install `uv` (one line) → single uvx config block → a 3-row client
  table (Claude Code / Codex / Claude Desktop).
- Demote tunnels, remote connectors (Cowork/ChatGPT), MCPB build, and
  marketplace install to an **Advanced** section.
- Remove all hardcoded `/Users/tim/...` paths.
- Move `pip install -e '.[dev]'` out of the user path into a short
  **Contributing** note.

### 4. Release tag

Create and push `v0.1.0` from the final merged commit so `@v0.1.0` references
resolve. The tag must come after the config changes are committed; verify
locally against a branch ref first, then tag.

## Verification

- `uvx --from git+<repo>@<branch-ref> 2do-mcp doctor` — cold-start resolves
  `fastmcp` + `pydantic`; warm-start is sub-second.
- `2do-mcp serve` via the same path launches and completes an MCP handshake.

## Out of scope

- PyPI publishing (GitHub-only for now).
- Any change to server behavior, tools, or backup logic.
