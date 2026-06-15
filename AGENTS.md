# Project Notes

- Prefer connector tools first (GitHub, Netlify, etc.) for discovery, status,
  logs, metadata, and comments; use CLI/API shell fallbacks only when connector
  support is missing.
- 2Do Tools is macOS-only and reads from a local 2Do backup. Do not commit real
  task data, database files, screenshots with private tasks, credentials, tunnel
  URLs, or machine-specific config. Tests use synthetic data.
- Use current names: repo/package `2do-tools`, Python package `_2do_tools`,
  command `2do`, server command `2do mcp serve`. Treat `2do-mcp` as legacy only.
- Keep changes tight: prefer modifying existing code/docs/tests over adding new
  scaffolding, and add tests only for meaningful behavior or regression risk.
- Keep `docs/` local-only and ignored. Never force-add or commit files under
  `docs/`, including plans, specifications, or generated documentation.
- Use `uv`: setup with `uv sync --extra dev`; checks are
  `git ls-files '*.py' -z | xargs -0 python3 -m py_compile`,
  `uv run --extra dev ruff check .`, `uv run --extra dev ruff format --check .`,
  and `uv run --extra dev pytest -q`. Keep `uv.lock` tracked for frozen CI.
- Keep MCP install/distribution centered on the refreshed stable Git ref:
  `uvx --refresh-package 2do-tools --from git+https://github.com/kingfink/2do-tools@stable 2do mcp serve`.
  Semantic version tags remain immutable release identifiers, and release
  automation preserves stable install refs while updating version-specific
  metadata.
  For releases, update `pyproject.toml`, `uv.lock`, `README.md`, `.mcp.json`,
  `plugins/2do/.mcp.json`, `mcpb/manifest.json`, and `mcpb/server.py` together.
- `plugins/2do/` is the plugin source of truth; root marketplace files only
  point there. MCPB should stay lightweight: manifest, README, and the minimal
  `server.py` entry point, not bundled source or dependencies.
- Keep the MCP tool surface read-oriented and focused. URL scheme tools open
  views on the host Mac; task creation/completion needs explicit confirmation
  and callback handling. Expose HTTP transport only behind HTTPS plus real auth.
