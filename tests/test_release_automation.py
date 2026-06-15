import importlib.util
import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STABLE_GIT_REF = "git+https://github.com/kingfink/2do-tools@stable"
STABLE_UVX_ARGS = [
    "--refresh-package",
    "2do-tools",
    "--from",
    STABLE_GIT_REF,
    "2do",
    "mcp",
    "serve",
]


def load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_stable_uvx_args(args: list[str]) -> None:
    assert args == STABLE_UVX_ARGS


def run_release_script(
    tmp_path: Path,
    *,
    release_exists: bool,
    release_commit: str = "release-commit",
    tag_commit: str = "release-commit",
    tag_resolution_fails: bool = False,
    remote_tag_exists: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    fake_bin = tmp_path / "bin"
    scripts_dir.mkdir(parents=True)
    fake_bin.mkdir()
    (repo_root / "mcpb").mkdir()
    (repo_root / "mcpb" / "manifest.json").write_text('{"version": "1.2.3"}')

    release_script = scripts_dir / "release.sh"
    release_script.write_text((REPO_ROOT / "scripts" / "release.sh").read_text())
    release_script.chmod(0o755)

    build_script = scripts_dir / "build-mcpb.sh"
    build_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'build\\n' >> "$COMMAND_LOG"
mkdir -p dist
: > dist/2do-tools.mcpb
"""
    )
    build_script.chmod(0o755)

    fake_git = fake_bin / "git"
    fake_git.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'git %s\\n' "$*" >> "$COMMAND_LOG"
if [[ "$1" == "status" && "${2:-}" == "--porcelain" ]]; then
  exit 0
fi
if [[ "$1" == "rev-parse" && "${2:-}" == "HEAD" ]]; then
  printf '%s\\n' "$RELEASE_COMMIT"
  exit 0
fi
if [[ "$1" == "rev-parse" && "${2:-}" == "$RELEASE_TAG^{commit}" ]]; then
  if [[ "$TAG_RESOLUTION_FAILS" == "1" ]]; then
    exit 1
  fi
  printf '%s\\n' "$TAG_COMMIT"
  exit 0
fi
if [[ "$1" == "ls-remote" && "${2:-}" == "--tags" ]]; then
  if [[ "$REMOTE_TAG_EXISTS" == "1" || -f "$RELEASE_CREATED_FILE" ]]; then
    printf '%s\\trefs/tags/%s\\n' "$TAG_COMMIT" "$RELEASE_TAG"
  fi
  exit 0
fi
if [[ "$1" == "fetch" ]]; then
  exit 0
fi
if [[ "$1" == "push" ]]; then
  exit 0
fi
printf 'Unexpected git command: %s\\n' "$*" >&2
exit 2
"""
    )
    fake_git.chmod(0o755)

    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'gh %s\\n' "$*" >> "$COMMAND_LOG"
if [[ "$1" == "release" && "$2" == "view" ]]; then
  [[ "$RELEASE_EXISTS" == "1" ]]
  exit
fi
if [[ "$1" == "release" && "$2" == "create" ]]; then
  : > "$RELEASE_CREATED_FILE"
  exit 0
fi
if [[ "$1" == "release" && "$2" == "upload" ]]; then
  exit 0
fi
printf 'Unexpected gh command: %s\\n' "$*" >&2
exit 2
"""
    )
    fake_gh.chmod(0o755)

    command_log = tmp_path / "commands.log"
    command_log.touch()
    env = os.environ | {
        "COMMAND_LOG": str(command_log),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "RELEASE_COMMIT": release_commit,
        "RELEASE_CREATED_FILE": str(tmp_path / "release-created"),
        "RELEASE_EXISTS": "1" if release_exists else "0",
        "RELEASE_TAG": "v1.2.3",
        "REMOTE_TAG_EXISTS": "1" if remote_tag_exists else "0",
        "TAG_COMMIT": tag_commit,
        "TAG_RESOLUTION_FAILS": "1" if tag_resolution_fails else "0",
    }
    result = subprocess.run(
        [str(release_script), "v1.2.3"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, command_log.read_text().splitlines()


def test_prepare_release_stages_all_release_metadata_files() -> None:
    script = (REPO_ROOT / "scripts" / "prepare-release.sh").read_text()

    for metadata_file in [
        ".mcp.json",
        "README.md",
        "plugins/2do/.mcp.json",
        "pyproject.toml",
        "uv.lock",
        "mcpb/manifest.json",
        "mcpb/server.py",
    ]:
        assert metadata_file in script

    assert 'git diff --quiet -- "${release_metadata_files[@]}"' in script
    assert 'git add "${release_metadata_files[@]}"' in script


def test_release_advances_stable_after_github_publication() -> None:
    script = (REPO_ROOT / "scripts" / "release.sh").read_text()

    assert 'git push origin "$release_commit:refs/heads/stable" --force' in script
    assert "git push origin HEAD:refs/heads/stable --force" not in script


def test_new_release_pushes_release_commit_to_stable_after_create(tmp_path: Path) -> None:
    result, commands = run_release_script(tmp_path, release_exists=False)
    assert result.returncode == 0, result.stderr

    create_command = next(
        command for command in commands if command.startswith("gh release create")
    )
    stable_push = "git push origin release-commit:refs/heads/stable --force"
    tag_fetch = "git fetch --force origin refs/tags/v1.2.3:refs/tags/v1.2.3"
    tag_resolve = "git rev-parse v1.2.3^{commit}"

    assert "--target release-commit" in create_command
    assert commands.index("git ls-remote --tags origin refs/tags/v1.2.3") < commands.index(
        create_command
    )
    assert commands.index(create_command) < commands.index(tag_fetch)
    assert commands.index(tag_fetch) < commands.index(tag_resolve)
    assert commands.index(tag_resolve) < commands.index(stable_push)


def test_existing_release_pushes_matching_release_commit_after_upload(tmp_path: Path) -> None:
    result, commands = run_release_script(tmp_path, release_exists=True)
    assert result.returncode == 0, result.stderr

    upload_command = next(
        command for command in commands if command.startswith("gh release upload")
    )
    stable_push = "git push origin release-commit:refs/heads/stable --force"

    assert commands.index(
        "git fetch --force origin refs/tags/v1.2.3:refs/tags/v1.2.3"
    ) < commands.index("git rev-parse v1.2.3^{commit}")
    assert commands.index("git rev-parse v1.2.3^{commit}") < commands.index(upload_command)
    assert commands.index(upload_command) < commands.index(stable_push)


def test_new_release_rejects_existing_mismatched_remote_tag(tmp_path: Path) -> None:
    result, commands = run_release_script(
        tmp_path,
        release_exists=False,
        remote_tag_exists=True,
        tag_commit="different-commit",
    )

    assert result.returncode != 0
    assert "does not match current release commit" in result.stderr
    assert "git ls-remote --tags origin refs/tags/v1.2.3" in commands
    assert "git fetch --force origin refs/tags/v1.2.3:refs/tags/v1.2.3" in commands
    assert "git rev-parse v1.2.3^{commit}" in commands
    assert not any(command.startswith("gh release create") for command in commands)
    assert not any(command.startswith("gh release upload") for command in commands)
    assert not any(command.startswith("git push") for command in commands)


def test_existing_release_rejects_mismatched_tag_commit(tmp_path: Path) -> None:
    result, commands = run_release_script(
        tmp_path,
        release_exists=True,
        tag_commit="different-commit",
    )

    assert result.returncode != 0
    assert "does not match current release commit" in result.stderr
    assert not any(command.startswith("gh release upload") for command in commands)
    assert not any(command.startswith("git push") for command in commands)


def test_existing_release_requires_resolvable_local_tag(tmp_path: Path) -> None:
    result, commands = run_release_script(
        tmp_path,
        release_exists=True,
        tag_resolution_fails=True,
    )

    assert result.returncode != 0
    assert "Unable to resolve local tag v1.2.3 to a commit" in result.stderr
    assert not any(command.startswith("gh release upload") for command in commands)
    assert not any(command.startswith("git push") for command in commands)


def test_product_metadata_describes_reading_creating_and_completing_tasks() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    mcpb_manifest = json.loads((REPO_ROOT / "mcpb" / "manifest.json").read_text())
    codex_plugin = json.loads(
        (REPO_ROOT / "plugins" / "2do" / ".codex-plugin" / "plugin.json").read_text()
    )
    claude_plugin = json.loads(
        (REPO_ROOT / "plugins" / "2do" / ".claude-plugin" / "plugin.json").read_text()
    )

    descriptions = [
        pyproject["project"]["description"],
        mcpb_manifest["description"],
        codex_plugin["description"],
        claude_plugin["description"],
    ]
    assert all(
        "read, create, and complete tasks" in description.lower() for description in descriptions
    )
    assert "read-only MCP server" not in mcpb_manifest["long_description"]
    assert "read-only MCP server" not in codex_plugin["interface"]["longDescription"]


def test_mcpb_manifest_lists_task_mutation_tools() -> None:
    manifest = json.loads((REPO_ROOT / "mcpb" / "manifest.json").read_text())

    tool_names = {tool["name"] for tool in manifest["tools"]}
    assert {"open_task_quick_entry", "create_task", "complete_task"} <= tool_names


def test_mcp_configs_launch_from_the_stable_git_ref() -> None:
    root_config = json.loads((REPO_ROOT / ".mcp.json").read_text())
    plugin_config = json.loads((REPO_ROOT / "plugins" / "2do" / ".mcp.json").read_text())
    manifest = json.loads((REPO_ROOT / "mcpb" / "manifest.json").read_text())

    assert_stable_uvx_args(root_config["mcpServers"]["2do"]["args"])
    assert_stable_uvx_args(plugin_config["mcpServers"]["2do"]["args"])
    assert_stable_uvx_args(manifest["server"]["mcp_config"]["args"])


def test_mcpb_server_launches_from_the_stable_git_ref() -> None:
    server = load_module("mcpb_server", "mcpb/server.py")

    assert server.GIT_REF == STABLE_GIT_REF
    assert server.COMMAND == ("uvx", *STABLE_UVX_ARGS)


def test_repo_install_ref_pattern_recognizes_stable() -> None:
    release_metadata = load_module("release_metadata", "scripts/release_metadata.py")

    match = release_metadata.REPO_INSTALL_REF_RE.fullmatch(STABLE_GIT_REF)

    assert match is not None
    assert match.group("ref") == "stable"


@pytest.mark.parametrize(
    "delimiter",
    [
        "",
        " ",
        "\n",
        '"',
        "'",
        "`",
        ",",
        ")",
        "]",
        "}",
        ">",
    ],
)
def test_repo_install_ref_pattern_accepts_source_delimiters(delimiter: str) -> None:
    release_metadata = load_module("release_metadata", "scripts/release_metadata.py")

    match = release_metadata.REPO_INSTALL_REF_RE.search(STABLE_GIT_REF + delimiter)

    assert match is not None
    assert match.group(0) == STABLE_GIT_REF


@pytest.mark.parametrize(
    "ref",
    [
        "stable/next",
        "stable+next",
        "stable@next",
        "stable-next",
        "stable123",
        "stable_next",
        "stable.next",
        "stable?next",
        "stable#next",
        "v1.2.3-next",
        "v1.2.3rc1",
    ],
)
def test_repo_install_ref_pattern_rejects_ref_continuations(ref: str) -> None:
    release_metadata = load_module("release_metadata", "scripts/release_metadata.py")
    install_ref = STABLE_GIT_REF.removesuffix("stable") + ref

    assert release_metadata.REPO_INSTALL_REF_RE.search(install_ref) is None


def test_update_repo_install_refs_preserves_stable(tmp_path, monkeypatch) -> None:
    release_metadata = load_module("release_metadata", "scripts/release_metadata.py")
    config_path = tmp_path / "config.json"
    install_ref_prefix = STABLE_GIT_REF.removesuffix("stable")
    config_path.write_text(f"{STABLE_GIT_REF}\n{install_ref_prefix}v0.8.0\n")
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)

    release_metadata.update_repo_install_refs("config.json", "v9.9.9")

    assert config_path.read_text() == f"{STABLE_GIT_REF}\n{install_ref_prefix}v9.9.9\n"
