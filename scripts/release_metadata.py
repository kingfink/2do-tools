#!/usr/bin/env python3
"""Update and verify release metadata for 2do-tools."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$")
VERSION_TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")
PYPROJECT_VERSION_RE = re.compile(r'version = "[0-9]+\.[0-9]+\.[0-9]+"')
REPO_INSTALL_REF_RE = re.compile(
    r"git\+https://github\.com/kingfink/2do-tools@"
    r"(?P<ref>stable|v[0-9]+\.[0-9]+\.[0-9]+)"
)
UV_LOCK_PROJECT_VERSION_RE = re.compile(
    r'(?ms)(\[\[package\]\]\nname = "2do-tools"\nversion = ")[^"]+(")'
)

SKIPPED_FALLBACK_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".uv-cache"}


def repo_path(relative_path: str) -> Path:
    return REPO_ROOT / relative_path


def release_version(tag: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise SystemExit(f"Tag must look like vX.Y.Z (got: {tag})")

    return match.group("version")


def project_version() -> str:
    project = tomllib.loads(repo_path("pyproject.toml").read_text())
    return project["project"]["version"]


def tracked_paths() -> list[str]:
    if (REPO_ROOT / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=False,
            )
        except (OSError, subprocess.CalledProcessError):
            pass
        else:
            return [path.decode() for path in result.stdout.split(b"\0") if path]

    paths: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue

        if any(part in SKIPPED_FALLBACK_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue

        paths.append(path.relative_to(REPO_ROOT).as_posix())

    return sorted(paths)


def tracked_text_files() -> list[str]:
    text_files: list[str] = []

    for relative_path in tracked_paths():
        path = repo_path(relative_path)
        try:
            path.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        text_files.append(relative_path)

    return text_files


def update_text(relative_path: str, replacements: list[tuple[re.Pattern[str], str]]) -> None:
    path = repo_path(relative_path)
    content = path.read_text()
    updated = content

    for pattern, replacement in replacements:
        updated = pattern.sub(replacement, updated)

    if updated != content:
        path.write_text(updated)


def replace_text(relative_path: str, old: str, new: str) -> None:
    path = repo_path(relative_path)
    content = path.read_text()
    updated = content.replace(old, new)

    if updated != content:
        path.write_text(updated)


def update_repo_install_refs(relative_path: str, tag: str) -> None:
    path = repo_path(relative_path)
    content = path.read_text()
    updated = REPO_INSTALL_REF_RE.sub(
        lambda match: (
            match.group(0)
            if match.group("ref") == "stable"
            else match.group(0).replace(match.group("ref"), tag)
        ),
        content,
    )

    if updated != content:
        path.write_text(updated)


def update_uv_lock_project_version(version: str) -> None:
    path = repo_path("uv.lock")
    if not path.exists():
        return

    content = path.read_text()
    updated, count = UV_LOCK_PROJECT_VERSION_RE.subn(
        lambda match: f"{match.group(1)}{version}{match.group(2)}",
        content,
        count=1,
    )

    if count == 0:
        raise SystemExit("uv.lock does not contain a 2do-tools package entry")

    if updated != content:
        path.write_text(updated)


def uv_lock_project_version() -> str | None:
    path = repo_path("uv.lock")
    if not path.exists():
        return None

    match = UV_LOCK_PROJECT_VERSION_RE.search(path.read_text())
    if match is None:
        return None

    return match.group(0).split('version = "', 1)[1].split('"', 1)[0]


def update_release_metadata(tag: str) -> None:
    version = release_version(tag)
    old_tag = f"v{project_version()}"

    update_text("pyproject.toml", [(PYPROJECT_VERSION_RE, f'version = "{version}"')])

    for file_name in tracked_text_files():
        replace_text(file_name, old_tag, tag)
        update_repo_install_refs(file_name, tag)

    manifest_path = repo_path("mcpb/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = version

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    update_uv_lock_project_version(version)


def verify_release_metadata(tag: str) -> None:
    version = release_version(tag)

    manifest = json.loads(repo_path("mcpb/manifest.json").read_text())

    if project_version() != version:
        raise SystemExit("pyproject.toml version does not match requested release")

    if manifest["version"] != version:
        raise SystemExit("mcpb/manifest.json version does not match requested release")

    lock_version = uv_lock_project_version()
    if lock_version is not None and lock_version != version:
        raise SystemExit("uv.lock 2do-tools version does not match requested release")

    found_install_ref = False
    stale_tags = []
    for file_name in tracked_text_files():
        content = repo_path(file_name).read_text()
        for match in REPO_INSTALL_REF_RE.finditer(content):
            found_install_ref = True
            ref = match.group("ref")
            if ref != "stable" and ref != tag:
                stale_tags.append(f"{file_name}: {ref}")

    if not found_install_ref:
        raise SystemExit("No 2do-tools git install references found")

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
