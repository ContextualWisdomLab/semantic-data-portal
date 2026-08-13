# Changelog

All notable changes to Semantic Data Portal are documented in this file.

## [Unreleased]

### Fixed

- Removed the production query executor's synthetic `mock-trino` success response. Governed SQL dry-runs now return validation-only evidence, while non-dry-run requests fail closed with `UNAVAILABLE` until a real execution backend is configured and invoked.

### Security

- Query policy and SQL safety validation remain authoritative before either validation-only or unavailable responses; no dataset profile value is reclassified as executed query output.
