#!/usr/bin/env python3
"""MCPB entry point for 2do-tools.

The bundle does not ship the server source or its dependencies. The actual
launch is driven by ``server.mcp_config`` in manifest.json, which runs the
server via ``uvx`` from the moving stable branch. This file is the
manifest-required ``entry_point`` and performs the same ``uvx`` launch when a
client execs the entry point directly. Both paths require ``uv`` to be
installed.
"""

import os
import sys

GIT_REF = "git+https://github.com/kingfink/2do-tools@stable"
COMMAND = ("uvx", "--refresh-package", "2do-tools", "--from", GIT_REF, "2do", "mcp", "serve")


def main() -> int:
    try:
        os.execvp(COMMAND[0], list(COMMAND))
    except FileNotFoundError:
        sys.stderr.write(
            "uvx not found. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
