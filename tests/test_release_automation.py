import importlib.util
import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STABLE_GIT_REF = "git+https://github.com/kingfink/2do-tools@stable"


def load_release_metadata():
    script_path = REPO_ROOT / "scripts" / "release_metadata.py"
    spec = importlib.util.spec_from_file_location("release_metadata", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_stable_uvx_args(args: list[str]) -> None:
    assert args[:4] == [
        "--refresh-package",
        "2do-tools",
        "--from",
        STABLE_GIT_REF,
    ]
    assert args[-3:] == ["2do", "mcp", "serve"]


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
    server = (REPO_ROOT / "mcpb" / "server.py").read_text()

    assert f'GIT_REF = "{STABLE_GIT_REF}"' in server
    assert '"uvx", "--refresh-package", "2do-tools", "--from", GIT_REF' in server


def test_repo_install_ref_pattern_recognizes_stable() -> None:
    release_metadata = load_release_metadata()

    match = release_metadata.REPO_INSTALL_REF_RE.fullmatch(STABLE_GIT_REF)

    assert match is not None
    assert match.group("ref") == "stable"


def test_update_repo_install_refs_preserves_stable(tmp_path, monkeypatch) -> None:
    release_metadata = load_release_metadata()
    config_path = tmp_path / "config.json"
    install_ref_prefix = STABLE_GIT_REF.removesuffix("stable")
    config_path.write_text(f"{STABLE_GIT_REF}\n{install_ref_prefix}v0.8.0\n")
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)

    release_metadata.update_repo_install_refs("config.json", "v9.9.9")

    assert config_path.read_text() == f"{STABLE_GIT_REF}\n{install_ref_prefix}v9.9.9\n"
