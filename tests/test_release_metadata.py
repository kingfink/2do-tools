import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_METADATA_PATH = REPO_ROOT / "scripts" / "release_metadata.py"
spec = importlib.util.spec_from_file_location("release_metadata", RELEASE_METADATA_PATH)
assert spec is not None
assert spec.loader is not None
release_metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_metadata)


def _write_release_files(root: Path, *, stale_root_ref: bool, stale_plugin_ref: bool) -> None:
    (root / "mcpb").mkdir()
    (root / "plugins" / "2do").mkdir(parents=True)

    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'version = "0.5.0"',
                "",
            ]
        )
    )
    (root / "README.md").write_text("Install git+https://github.com/kingfink/2do-tools@v0.5.0\n")
    (root / "mcpb" / "server.py").write_text(
        'GIT_REF = "git+https://github.com/kingfink/2do-tools@v0.5.0"\n'
    )
    (root / "mcpb" / "manifest.json").write_text(
        """
{
  "version": "0.5.0",
  "server": {
    "mcp_config": {
      "args": [
        "--from",
        "git+https://github.com/kingfink/2do-tools@v0.5.0"
      ]
    }
  }
}
""".lstrip()
    )

    root_tag = "v0.3.0" if stale_root_ref else "v0.5.0"
    plugin_tag = "v0.3.0" if stale_plugin_ref else "v0.5.0"

    root_mcp_json = f"""
{{
  "mcpServers": {{
    "2do": {{
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/kingfink/2do-tools@{root_tag}",
        "2do",
        "mcp",
        "serve"
      ]
    }}
  }}
}}
""".lstrip()
    plugin_mcp_json = root_mcp_json.replace(f"@{root_tag}", f"@{plugin_tag}")
    (root / ".mcp.json").write_text(root_mcp_json)
    (root / "plugins" / "2do" / ".mcp.json").write_text(plugin_mcp_json)


def test_verify_release_metadata_checks_plugin_mcp_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_release_files(tmp_path, stale_root_ref=False, stale_plugin_ref=True)
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="plugins/2do/.mcp.json"):
        release_metadata.verify_release_metadata("v0.5.0")


def test_update_release_metadata_updates_plugin_mcp_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_release_files(tmp_path, stale_root_ref=True, stale_plugin_ref=True)
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)

    release_metadata.update_release_metadata("v0.6.0")

    assert "@v0.6.0" in (tmp_path / ".mcp.json").read_text()
    assert "@v0.6.0" in (tmp_path / "plugins" / "2do" / ".mcp.json").read_text()
    release_metadata.verify_release_metadata("v0.6.0")
