# Contributing

Thanks for helping improve 2Do Tools.

## Privacy

Do not commit real 2Do database files, task exports, screenshots containing
private tasks, local credentials, tunnel URLs, or machine-specific config.
Tests should use synthetic task data only.

## Local Setup

```bash
uv sync --extra dev
```

Run the server from your checkout:

```bash
uv run 2do mcp serve
```

Install the CLI from a checkout:

```bash
uv tool install --editable .
uv tool update-shell
```

Run checks before opening a pull request:

```bash
git ls-files '*.py' -z | xargs -0 python3 -m py_compile
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev pytest -q
```

## Pull Requests

Keep changes focused, include tests for behavior changes, and update README or
plugin metadata when install instructions change.

## Claude Desktop Bundle

Install the MCPB CLI and build the bundle from a checkout:

```bash
npm install -g @anthropic-ai/mcpb
scripts/build-mcpb.sh
```

The script writes `dist/2do-tools.mcpb`.

## Release

Releases use a two-step flow: prepare a version-bump PR, then publish the
GitHub release from CI after that PR merges.

Prepare the release PR from GitHub Actions:

1. Open Actions > Prepare Release PR > Run workflow.
2. Enter the tag, such as `v0.6.0`.
3. Merge the generated PR after CI passes.

The workflow needs permission to create pull requests. Enable Settings >
Actions > General > Workflow permissions > Allow GitHub Actions to create and
approve pull requests. If a run pushes the release branch but cannot open the
PR, fix the permission and rerun the workflow with the same tag.

To prepare the same PR locally instead, run this from a clean checkout:

```bash
scripts/prepare-release.sh v0.6.0
```

`scripts/prepare-release.sh` checks out `master`, pulls the latest
`origin/master`, creates `codex/release-v0.6.0`, updates release metadata, runs
the standard checks, commits the version bump, pushes the release branch, and
opens the PR. The shared release metadata logic lives in
`scripts/release_metadata.py`.

After the PR merges, publish the release from GitHub Actions:

1. Open Actions > Release > Run workflow.
2. Enter the same tag, such as `v0.6.0`.
3. Run the workflow from `master`.

The workflow verifies that release metadata matches the tag, runs
`scripts/release.sh`, validates and packs `dist/2do-tools.mcpb`, uploads the
bundle asset, and creates the remote tag at the current `master` commit.
