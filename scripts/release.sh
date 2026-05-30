#!/usr/bin/env bash
set -euo pipefail

# Cut a release: tag the current commit and publish a GitHub Release with the
# prebuilt MCPB bundle attached. Run from a clean checkout of the commit you
# want to release (normally master after the distribution PR has merged).
#
# Usage: scripts/release.sh v0.1.0

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "Usage: scripts/release.sh <tag>   (e.g. scripts/release.sh v0.1.0)" >&2
  exit 1
fi

if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Tag must look like vX.Y.Z (got: $tag)" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install it: https://cli.github.com/" >&2
  exit 1
fi

# Refuse to release a dirty tree — the bundle must match the tagged commit.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash changes before releasing." >&2
  exit 1
fi

# Warn if the manifest version does not match the tag (e.g. tag v0.2.0 but
# manifest still says 0.1.0). Usually a mistake worth catching.
manifest_version="$(python3 -c 'import json; print(json.load(open("mcpb/manifest.json"))["version"])')"
if [[ "$tag" != "v$manifest_version" ]]; then
  echo "Warning: tag $tag does not match mcpb/manifest.json version $manifest_version" >&2
fi

echo "Building MCPB bundle..."
scripts/build-mcpb.sh

echo "Tagging $tag..."
git tag -a "$tag" -m "2do-mcp $tag"
git push origin "$tag"

echo "Creating GitHub release $tag with the bundle attached..."
gh release create "$tag" \
  "$repo_root/dist/2do-mcp.mcpb" \
  --title "2do-mcp $tag" \
  --generate-notes

echo "Done. Release $tag published with dist/2do-mcp.mcpb attached."
