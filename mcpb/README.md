# Claude Desktop MCPB Scaffold

This directory contains the MCPB manifest and entry point used to package
2Do MCP as a Claude Desktop extension.

Build from the repository root:

```bash
scripts/build-mcpb.sh
```

The script creates a temporary bundle directory under `dist/mcpb/2do-mcp` and
packs `dist/2do-mcp.mcpb`.

Install the MCPB CLI first if needed:

```bash
npm install -g @anthropic-ai/mcpb
```

Claude Desktop can install the generated `.mcpb` by double-clicking it, dragging
it into the Claude Desktop window, or using Settings > Extensions > Advanced
settings > Install Extension.
