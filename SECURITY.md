# Security Policy

## Supported Versions

Security fixes are handled on the latest released version of `2do-tools`.

## Reporting a Vulnerability

Please do not include private task data, database files, screenshots with task
contents, access tokens, or other sensitive information in public issues.

If GitHub private vulnerability reporting is enabled for this repository, use
the repository's "Report a vulnerability" flow. Otherwise, open a public issue
with a minimal description that does not reveal exploit details or private data,
and the maintainer can coordinate next steps.

## Local Data Expectations

This project reads a local 2Do database backup from the Mac running the server.
Do not expose the HTTP MCP transport to the public internet unless it is behind
HTTPS and authentication that restricts access to trusted users only.
