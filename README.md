# TODOs

- [ ] Validate every SQLite column used by task, calendar, and tag queries before accepting a snapshot.
- [ ] Package the server with a real entry point so MCP clients do not depend on a checked-out `venv/bin/python`.
- [ ] Add automatic snapshot refresh with a sensible default interval.
- [ ] Track the source database path used for the snapshot so refresh can compare source `2do.db*` mtimes against the local snapshot and skip unchanged copies.
- [ ] Make tag filtering delimiter-aware instead of using substring `LIKE` matching.
- [ ] Add richer task tools and filters:
  - [ ] list calendars
  - [ ] list tags
  - [ ] get overdue tasks
  - [ ] get tasks due today
  - [ ] get upcoming tasks
  - [ ] search or filter tasks by list, tag, due range, and completion state
- [ ] Add tests for timestamp sentinel handling, tag parsing, SQL filter construction, schema validation, and snapshot promotion.
- [ ] Expand the README with setup, MCP client configuration, privacy/data behavior, and snapshot refresh behavior.
