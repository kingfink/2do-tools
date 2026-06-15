import importlib.util
import json
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
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_release_repo(tmp_path: Path, refs: list[str]) -> None:
    (tmp_path / "mcpb").mkdir(exist_ok=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
    (tmp_path / "mcpb" / "manifest.json").write_text('{"version": "1.2.3"}\n')
    (tmp_path / "install-refs.txt").write_text("\n".join(refs) + "\n")


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


def test_product_metadata_describes_reading_creating_and_completing_tasks() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    mcpb_manifest = json.loads((REPO_ROOT / "mcpb" / "manifest.json").read_text())
    plugin_paths = [
        REPO_ROOT / "plugins" / "2do" / ".codex-plugin" / "plugin.json",
        REPO_ROOT / "plugins" / "2do" / ".claude-plugin" / "plugin.json",
    ]
    descriptions = [
        pyproject["project"]["description"],
        mcpb_manifest["description"],
        *(json.loads(path.read_text())["description"] for path in plugin_paths),
    ]

    assert all(
        "read, create, and complete tasks" in description.lower() for description in descriptions
    )
    assert "read-only MCP server" not in mcpb_manifest["long_description"]


def test_mcpb_manifest_lists_task_mutation_tools() -> None:
    manifest = json.loads((REPO_ROOT / "mcpb" / "manifest.json").read_text())
    tool_names = {tool["name"] for tool in manifest["tools"]}

    assert {"open_task_quick_entry", "create_task", "complete_task"} <= tool_names


def test_all_mcp_launchers_refresh_the_stable_ref() -> None:
    root_config = json.loads((REPO_ROOT / ".mcp.json").read_text())
    plugin_config = json.loads((REPO_ROOT / "plugins" / "2do" / ".mcp.json").read_text())
    manifest = json.loads((REPO_ROOT / "mcpb" / "manifest.json").read_text())
    server = load_module("mcpb_server", "mcpb/server.py")

    assert root_config["mcpServers"]["2do"]["args"] == STABLE_UVX_ARGS
    assert plugin_config["mcpServers"]["2do"]["args"] == STABLE_UVX_ARGS
    assert manifest["server"]["mcp_config"]["args"] == STABLE_UVX_ARGS
    assert server.GIT_REF == STABLE_GIT_REF
    assert server.COMMAND == ("uvx", *STABLE_UVX_ARGS)


def test_release_metadata_preserves_stable_and_updates_version_refs(
    tmp_path: Path, monkeypatch
) -> None:
    release_metadata = load_module("release_metadata", "scripts/release_metadata.py")
    old_ref = STABLE_GIT_REF.removesuffix("stable") + "v0.8.0"
    config = tmp_path / "config.txt"
    config.write_text(f"{STABLE_GIT_REF}\n{old_ref}\n")
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)

    release_metadata.update_repo_install_refs("config.txt", "v1.2.3")

    version_ref = STABLE_GIT_REF.removesuffix("stable") + "v1.2.3"
    assert config.read_text() == f"{STABLE_GIT_REF}\n{version_ref}\n"


def test_release_metadata_rejects_invalid_and_stale_refs(tmp_path: Path, monkeypatch) -> None:
    release_metadata = load_module("release_metadata", "scripts/release_metadata.py")
    prefix = STABLE_GIT_REF.removesuffix("stable")
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)

    write_release_repo(tmp_path, [STABLE_GIT_REF, prefix + "stable-next"])
    with pytest.raises(SystemExit, match="Found invalid release refs"):
        release_metadata.verify_release_metadata("v1.2.3")

    write_release_repo(tmp_path, [STABLE_GIT_REF, prefix + "v1.2.2"])
    with pytest.raises(SystemExit, match="Found stale release tags"):
        release_metadata.verify_release_metadata("v1.2.3")

    write_release_repo(tmp_path, [STABLE_GIT_REF, prefix + "v1.2.3"])
    release_metadata.verify_release_metadata("v1.2.3")


def test_verify_ignores_install_refs_inside_test_files(tmp_path: Path, monkeypatch) -> None:
    release_metadata = load_module("release_metadata", "scripts/release_metadata.py")
    prefix = STABLE_GIT_REF.removesuffix("stable")
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)

    write_release_repo(tmp_path, [STABLE_GIT_REF])
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_docs.py").write_text(f'assert "{prefix}v0.8.0" not in readme\n')

    release_metadata.verify_release_metadata("v1.2.3")


def test_release_script_verifies_tag_before_publication_and_stable_update() -> None:
    script = (REPO_ROOT / "scripts" / "release.sh").read_text()
    publication = script[
        script.index('if gh release view "$tag"') : script.index('echo "Updating stable branch')
    ]
    existing_release, new_release = publication.split("\nelse\n", maxsplit=1)

    assert existing_release.index("verify_release_tag") < existing_release.index(
        'gh release upload "$tag"'
    )
    assert new_release.index('remote_tag="$(git ls-remote') < new_release.index(
        'gh release create "$tag"'
    )
    assert '--target "$release_commit"' in new_release
    assert new_release.rindex("verify_release_tag") > new_release.index('gh release create "$tag"')
    assert 'git push origin "$release_commit:refs/heads/stable" --force' in script
    assert "git push origin HEAD:refs/heads/stable --force" not in script


def test_readme_documents_stable_installs_and_one_time_migration() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    uvx_prefix = f"uvx --refresh-package 2do-tools --from {STABLE_GIT_REF}"
    uvx_lines = [
        line
        for line in readme.splitlines()
        if "uvx" in line and "git+https://github.com/kingfink/2do-tools" in line
    ]

    assert uvx_lines and all(uvx_prefix in line for line in uvx_lines)
    assert "Existing installations pinned to a version tag do not switch automatically." in readme
    assert "fully quit and reopen" in readme
    assert "claude plugin marketplace update 2do-tools" in readme
    assert "claude plugin uninstall 2do@2do-tools" in readme
    assert "claude plugin install 2do@2do-tools" in readme
    assert f'uv tool install "{STABLE_GIT_REF}"' in readme
    assert "uv tool upgrade 2do-tools" in readme
    assert "git+https://github.com/kingfink/2do-tools@v0.8.0" not in readme
