---
name: 2do-daily-review
description: Use when reviewing, planning, or summarizing a day from a user's local 2Do tasks, including overdue, due today, upcoming, inbox, or recently completed tasks.
---

# 2Do Daily Review

Use the read-only `2do` CLI first. In MCP-only clients, use `list_tasks_overdue`, `list_tasks_due_today`, `list_tasks_inbox`, and `list_tasks_completed_today`.

Compute exact local dates before filtering. Use `TODAY` and `TOMORROW` as placeholders for those concrete dates.

- Overdue: `2do task list --has-due-date --due-before TODAY --json`
- Due today: `2do task list --has-due-date --due-from TODAY --due-before TOMORROW --json`
- Upcoming dated: `2do task list --has-due-date --due-from TOMORROW --json`
- Inbox: `2do task list --list Inbox --json`
- Completed today: `2do task list --completed --completed-from TODAY --completed-before TOMORROW --json`

Summarize by group with task title, list, tags, due date, and UID only when useful. Do not change tasks; only run `2do task open <uid>` if the user asks to open one in 2Do.
