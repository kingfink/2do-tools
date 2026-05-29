#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle_dir="$repo_root/dist/mcpb/2do-mcp"
output="$repo_root/dist/2do-mcp.mcpb"

if ! command -v mcpb >/dev/null 2>&1; then
  echo "mcpb CLI not found. Install it with: npm install -g @anthropic-ai/mcpb" >&2
  exit 1
fi

rm -rf "$bundle_dir"
mkdir -p "$bundle_dir"

cp "$repo_root/mcpb/manifest.json" "$bundle_dir/manifest.json"
cp "$repo_root/mcpb/.mcpbignore" "$bundle_dir/.mcpbignore"
cp "$repo_root/mcpb/server.py" "$bundle_dir/server.py"
cp "$repo_root/README.md" "$bundle_dir/README.md"

mcpb validate "$bundle_dir"
mcpb pack "$bundle_dir" "$output"

echo "Packed $output"
