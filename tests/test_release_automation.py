import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_product_metadata_describes_reading_and_creating_tasks() -> None:
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
    assert all("read and create tasks" in description.lower() for description in descriptions)
    assert "read-only MCP server" not in mcpb_manifest["long_description"]
    assert "read-only MCP server" not in codex_plugin["interface"]["longDescription"]


def test_mcpb_manifest_lists_task_creation_tools() -> None:
    manifest = json.loads((REPO_ROOT / "mcpb" / "manifest.json").read_text())

    tool_names = {tool["name"] for tool in manifest["tools"]}
    assert {"open_task_quick_entry", "create_task"} <= tool_names


def test_readme_distinguishes_database_access_from_task_creation() -> None:
    readme = (REPO_ROOT / "README.md").read_text()

    assert "Database access remains read-only" in readme
    assert "creation is delegated to 2Do through its documented URL scheme" in readme
    assert "2do task quick-entry" in readme
    assert "2do task create" in readme
