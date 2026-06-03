#!/usr/bin/env python3
"""Update and verify release metadata for 2do-tools."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$")
VERSION_TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")
PYPROJECT_VERSION_RE = re.compile(r'version = "[0-9]+\.[0-9]+\.[0-9]+"')
INSTALL_REF_RE = re.compile(r"@v[0-9]+\.[0-9]+\.[0-9]+")

INSTALL_REF_TEXT_FILES = ("README.md", "mcpb/server.py", ".mcp.json", "plugins/2do/.mcp.json")
INSTALL_REF_JSON_FILES = ("mcpb/manifest.json",)
INSTALL_REF_FILES = INSTALL_REF_TEXT_FILES + INSTALL_REF_JSON_FILES


def repo_path(relative_path: str) -> Path:
    return REPO_ROOT / relative_path


def release_version(tag: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise SystemExit(f"Tag must look like vX.Y.Z (got: {tag})")

    return match.group("version")


def update_text(relative_path: str, replacements: list[tuple[re.Pattern[str], str]]) -> None:
    path = repo_path(relative_path)
    content = path.read_text()
    updated = content

    for pattern, replacement in replacements:
        updated = pattern.sub(replacement, updated)

    if updated != content:
        path.write_text(updated)


def update_release_metadata(tag: str) -> None:
    version = release_version(tag)

    update_text("pyproject.toml", [(PYPROJECT_VERSION_RE, f'version = "{version}"')])
    update_text("README.md", [(VERSION_TAG_RE, tag)])

    for file_name in INSTALL_REF_TEXT_FILES:
        if file_name == "README.md":
            continue

        update_text(file_name, [(INSTALL_REF_RE, f"@{tag}")])

    manifest_path = repo_path("mcpb/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = version

    args = manifest["server"]["mcp_config"]["args"]
    manifest["server"]["mcp_config"]["args"] = [INSTALL_REF_RE.sub(f"@{tag}", arg) for arg in args]

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def verify_release_metadata(tag: str) -> None:
    version = release_version(tag)

    project = tomllib.loads(repo_path("pyproject.toml").read_text())
    manifest = json.loads(repo_path("mcpb/manifest.json").read_text())

    if project["project"]["version"] != version:
        raise SystemExit("pyproject.toml version does not match requested release")

    if manifest["version"] != version:
        raise SystemExit("mcpb/manifest.json version does not match requested release")

    for file_name in INSTALL_REF_FILES:
        content = repo_path(file_name).read_text()
        if f"@{tag}" not in content:
            raise SystemExit(f"{file_name} does not contain install reference @{tag}")

    stale_tags = []
    for file_name in INSTALL_REF_FILES:
        content = repo_path(file_name).read_text()
        stale_tags.extend(
            f"{file_name}: {match.group(0)}"
            for match in VERSION_TAG_RE.finditer(content)
            if match.group(0) != tag
        )

    if stale_tags:
        raise SystemExit("Found stale release tags:\n" + "\n".join(stale_tags))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    update_parser = subparsers.add_parser("update", help="update release metadata")
    update_parser.add_argument("tag", help="release tag, such as v0.3.0")

    verify_parser = subparsers.add_parser("verify", help="verify release metadata")
    verify_parser.add_argument("tag", help="release tag, such as v0.3.0")

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "update":
        update_release_metadata(args.tag)
    elif args.command == "verify":
        verify_release_metadata(args.tag)


if __name__ == "__main__":
    main()
