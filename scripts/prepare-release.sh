#!/usr/bin/env bash
set -euo pipefail

# Prepare a release PR by updating every version reference, running the standard
# checks, and committing the version bump on the current branch.
#
# Usage: scripts/prepare-release.sh v0.3.0

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "Usage: scripts/prepare-release.sh <tag>   (e.g. scripts/prepare-release.sh v0.3.0)" >&2
  exit 1
fi

if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Tag must look like vX.Y.Z (got: $tag)" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash changes before preparing a release." >&2
  exit 1
fi

version="${tag#v}"

python3 scripts/release_metadata.py update "$tag"

echo "Verifying release metadata..."
python3 scripts/release_metadata.py verify "$tag"

if git diff --quiet -- README.md pyproject.toml mcpb/manifest.json mcpb/server.py; then
  echo "No version reference changes found for $tag." >&2
  exit 1
fi

echo "Running checks..."
git ls-files '*.py' -z | xargs -0 python3 -m py_compile
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
python3 -m json.tool mcpb/manifest.json >/dev/null

git add README.md pyproject.toml mcpb/manifest.json mcpb/server.py
git commit -m "Bump version to $version"

echo "Prepared release $tag. Push this branch, open a PR, merge it, then run the Release workflow with tag $tag."
