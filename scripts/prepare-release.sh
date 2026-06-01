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

python3 - "$tag" "$version" <<'PY'
import json
import re
import sys
from pathlib import Path

tag = sys.argv[1]
version = sys.argv[2]


def update_text(path: str, replacements: list[tuple[str, str]]) -> None:
    file_path = Path(path)
    content = file_path.read_text()
    updated = content

    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, updated)

    if updated != content:
        file_path.write_text(updated)


update_text("pyproject.toml", [(r'version = "[0-9]+\.[0-9]+\.[0-9]+"', f'version = "{version}"')])
update_text("mcpb/server.py", [(r"@v[0-9]+\.[0-9]+\.[0-9]+", f"@{tag}")])
update_text("README.md", [(r"v[0-9]+\.[0-9]+\.[0-9]+", tag)])

manifest_path = Path("mcpb/manifest.json")
manifest = json.loads(manifest_path.read_text())
manifest["version"] = version

args = manifest["server"]["mcp_config"]["args"]
manifest["server"]["mcp_config"]["args"] = [
    re.sub(r"@v[0-9]+\.[0-9]+\.[0-9]+", f"@{tag}", arg) for arg in args
]

manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
PY

echo "Verifying release metadata..."
python3 - "$tag" "$version" <<'PY'
import json
import re
import sys
import tomllib
from pathlib import Path

tag = sys.argv[1]
version = sys.argv[2]

project = tomllib.loads(Path("pyproject.toml").read_text())
manifest = json.loads(Path("mcpb/manifest.json").read_text())

if project["project"]["version"] != version:
    raise SystemExit("pyproject.toml version does not match requested release")

if manifest["version"] != version:
    raise SystemExit("mcpb/manifest.json version does not match requested release")

versioned_files = ["README.md", "mcpb/manifest.json", "mcpb/server.py"]
for file_name in versioned_files:
    content = Path(file_name).read_text()
    if tag not in content:
        raise SystemExit(f"{file_name} does not contain {tag}")

stale = []
for file_name in ["README.md", "mcpb/manifest.json", "mcpb/server.py"]:
    content = Path(file_name).read_text()
    stale.extend(
        f"{file_name}: {match.group(0)}"
        for match in re.finditer(r"v[0-9]+\.[0-9]+\.[0-9]+", content)
        if match.group(0) != tag
    )

if stale:
    raise SystemExit("Found stale release tags:\n" + "\n".join(stale))
PY

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
