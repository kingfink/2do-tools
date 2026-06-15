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
