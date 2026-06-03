#!/usr/bin/env bash
set -euo pipefail

# Prepare a release PR by updating every version reference, running the standard
# checks, committing the version bump, pushing the release branch, and opening a
# pull request.
#
# Usage: scripts/prepare-release.sh v0.3.0

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/prepare-release.sh <tag> [options]

Prepare a release PR from the latest master.

Arguments:
  <tag>                  Release tag, such as v0.3.0.

Options:
  --base <branch>        Base branch to update from and open the PR against.
                         Defaults to master.
  --branch <branch>      Release branch to create. Defaults to codex/release-<tag>.
  --remote <remote>      Git remote to pull from and push to. Defaults to origin.
  --no-push              Commit locally but do not push or open the PR.
  --no-pr                Push the release branch but do not open the PR.
  -h, --help             Show this help.
USAGE
}

tag=""
base_branch="master"
remote="origin"
release_branch=""
push_branch=true
create_pr=true
release_metadata_files=(
  .mcp.json
  README.md
  plugins/2do/.mcp.json
  pyproject.toml
  uv.lock
  mcpb/manifest.json
  mcpb/server.py
)

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --base)
      base_branch="${2:-}"
      if [[ -z "$base_branch" ]]; then
        echo "--base requires a branch name." >&2
        exit 1
      fi
      shift 2
      ;;
    --branch)
      release_branch="${2:-}"
      if [[ -z "$release_branch" ]]; then
        echo "--branch requires a branch name." >&2
        exit 1
      fi
      shift 2
      ;;
    --remote)
      remote="${2:-}"
      if [[ -z "$remote" ]]; then
        echo "--remote requires a remote name." >&2
        exit 1
      fi
      shift 2
      ;;
    --no-push)
      push_branch=false
      create_pr=false
      shift
      ;;
    --no-pr)
      create_pr=false
      shift
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -n "$tag" ]]; then
        echo "Unexpected argument: $1" >&2
        usage
        exit 1
      fi
      tag="$1"
      shift
      ;;
  esac
done

if [[ -z "$tag" ]]; then
  usage
  exit 1
fi

if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Tag must look like vX.Y.Z (got: $tag)" >&2
  exit 1
fi

if [[ "$create_pr" == true ]] && ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install it: https://cli.github.com/" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash changes before preparing a release." >&2
  exit 1
fi

version="${tag#v}"
if [[ -z "$release_branch" ]]; then
  release_branch="codex/release-$tag"
fi

echo "Checking out $base_branch..."
git checkout "$base_branch"

echo "Updating $base_branch from $remote..."
git pull --ff-only "$remote" "$base_branch"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty after updating $base_branch." >&2
  exit 1
fi

release_branch_exists=false
release_branch_was_prepared=false
if git ls-remote --exit-code --heads "$remote" "$release_branch" >/dev/null 2>&1; then
  release_branch_exists=true
fi

if git show-ref --verify --quiet "refs/heads/$release_branch"; then
  echo "Checking out existing local release branch $release_branch..."
  git checkout "$release_branch"
  release_branch_was_prepared=true
elif [[ "$release_branch_exists" == true ]]; then
  echo "Checking out existing remote release branch $release_branch..."
  git fetch "$remote" "refs/heads/$release_branch:refs/remotes/$remote/$release_branch"
  git checkout --track -b "$release_branch" "$remote/$release_branch"
  release_branch_was_prepared=true
else
  echo "Creating release branch $release_branch..."
  git checkout -b "$release_branch"
fi

if [[ "$release_branch_exists" == true ]]; then
  echo "Updating $release_branch from $remote..."
  git pull --ff-only "$remote" "$release_branch"
fi

if [[ "$release_branch_was_prepared" == false ]]; then
  python3 scripts/release_metadata.py update "$tag"
fi

echo "Verifying release metadata..."
python3 scripts/release_metadata.py verify "$tag"

if [[ "$release_branch_was_prepared" == false ]] \
  && git diff --quiet -- "${release_metadata_files[@]}"; then
  echo "No version reference changes found for $tag." >&2
  exit 1
fi

echo "Running checks..."
git ls-files '*.py' -z | xargs -0 python3 -m py_compile
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
python3 -m json.tool mcpb/manifest.json >/dev/null

if [[ "$release_branch_was_prepared" == false ]]; then
  git add "${release_metadata_files[@]}"
  git commit -m "Bump version to $version"
fi

if [[ "$push_branch" == true ]]; then
  echo "Pushing $release_branch to $remote..."
  git push -u "$remote" "$release_branch"
else
  echo "Prepared release $tag on $release_branch without pushing."
fi

if [[ "$create_pr" == true ]]; then
  pr_title="Bump version to $tag"
  pr_body="Prepares release $tag.

After this PR merges, run the Release workflow with tag $tag."

  echo "Opening release PR..."
  pr_url="$(gh pr view "$release_branch" --json url --jq .url 2>/dev/null || true)"
  if [[ -z "$pr_url" ]]; then
    pr_create_output="$(
      gh pr create --base "$base_branch" --head "$release_branch" --title "$pr_title" --body "$pr_body" 2>&1
    )" || {
      echo "$pr_create_output" >&2

      if [[ "$pr_create_output" == *"GitHub Actions is not permitted to create or approve pull requests"* ]]; then
        cat >&2 <<EOF

GitHub blocked this workflow token from creating pull requests.

To allow the Prepare Release PR workflow to open the PR:
- Enable Settings > Actions > General > Workflow permissions > Allow GitHub Actions to create and approve pull requests.

The release branch was pushed successfully: $release_branch
EOF
      fi

      exit 1
    }
    pr_url="$pr_create_output"
  fi
  echo "Prepared release $tag PR: $pr_url"
  echo "Merge it, then run the Release workflow with tag $tag."
else
  echo "Prepared release $tag on $release_branch. Open a PR, merge it, then run the Release workflow with tag $tag."
fi
