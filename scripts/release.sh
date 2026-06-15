#!/usr/bin/env bash
set -euo pipefail

# Cut a release: tag the current commit and publish a GitHub Release with the
# prebuilt MCPB bundle attached. Run from a clean checkout of the commit you
# want to release (normally master after the distribution PR has merged).
#
# Usage: scripts/release.sh vX.Y.Z

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "Usage: scripts/release.sh <tag>   (e.g. scripts/release.sh v0.3.0)" >&2
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

echo "Creating GitHub release $tag with the bundle attached..."
if gh release view "$tag" >/dev/null 2>&1; then
  # Release already exists (e.g. retrying after a failure) — just refresh the
  # bundle asset rather than recreating the release.
  echo "Release $tag already exists; refreshing the bundle asset."
  gh release upload "$tag" "$repo_root/dist/2do-tools.mcpb" --clobber
else
  # Let gh create the tag at the current commit as part of publishing the
  # release (--target). The tag is created on the remote ONLY when the release
  # succeeds, so a failed run never leaves a dangling tag behind, and there is
  # no local tag to get out of sync. Do not pre-create a local tag: gh refuses
  # to publish if a same-named local tag exists but has not been pushed.
  gh release create "$tag" \
    "$repo_root/dist/2do-tools.mcpb" \
    --title "2do-tools $tag" \
    --generate-notes \
    --target "$(git rev-parse HEAD)"
fi

echo "Updating stable branch to $tag..."
git push origin HEAD:refs/heads/stable --force

echo "Done. Release $tag published, stable updated, and dist/2do-tools.mcpb attached."
