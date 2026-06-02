---
name: 2do-task-lookup
description: Use when the user wants to find, filter, search, list, or open tasks, lists, tags, or saved searches from the local 2Do app.
---

# 2Do Task Lookup

Prefer the CLI:

- Tasks: `2do task list --json [--query TEXT] [--list NAME] [--tag NAME] [--has-due-date] [--due-from YYYY-MM-DD] [--due-before YYYY-MM-DD] [--completed] [--all] [--limit N]`
- Lists and tags: `2do list list --json`, `2do tag list --json`
- Open in 2Do: `2do task open <uid>`, `2do list open <name>`, or `2do search open <query>`

Use MCP equivalents only in MCP-only clients: `list_tasks`, `list_lists`, `list_tags`, `open_task`, `open_list`, and `open_search`.

Use exact dates for relative requests. Summarize matches before opening when the query is ambiguous. Do not modify tasks.
