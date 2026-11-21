# Claude Desktop MCPB Scaffold

This directory contains the MCPB manifest and entry point used to package
2Do Tools as a Claude Desktop extension.

Requires macOS on Apple Silicon (arm64) with native arm64 Python 3.11 or newer. Intel Macs and Python running under Rosetta are not supported.

Build from the repository root:

```bash
scripts/build-mcpb.sh
```

The script creates a temporary bundle directory under `dist/mcpb/2do-tools` and
packs `dist/2do-tools.mcpb`.

Install the MCPB CLI first if needed:

```bash
npm install -g @anthropic-ai/mcpb
```

Claude Desktop can install the generated `.mcpb` by double-clicking it, dragging
it into the Claude Desktop window, or using Settings > Extensions > Advanced
settings > Install Extension.
