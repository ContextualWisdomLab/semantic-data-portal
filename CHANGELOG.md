# Changelog

All notable changes to Semantic Data Portal are documented in this file.

## [Unreleased]

### Fixed

- Removed the production query executor's synthetic `mock-trino` success response. Governed SQL dry-runs now return validation-only evidence, while non-dry-run requests fail closed with `UNAVAILABLE` until a real execution backend is configured and invoked.

### Security

- Query policy and SQL safety validation remain authoritative before either validation-only or unavailable responses; no dataset profile value is reclassified as executed query output.
- The changed-production coverage gate now validates git object names and source roots, then invokes `git diff` with an argument vector and `shell=False`, so diff path text cannot be treated as a shell command.
- `get_config_entry()` caches a bounded number of single-key KV reads so credential lookups do not open a new engine on every observability export.
- Query drafts now join a fixed SELECT from reviewed identifier and integer tokens. Date windows are `current_date - N`, so user-controlled numbers never enter a SQL string literal.
- Local `file:` observability sinks reject non-empty remote authorities so `file://host/share` cannot become a UNC path that bypasses the HTTPS egress boundary.
