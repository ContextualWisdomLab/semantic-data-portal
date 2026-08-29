# Changelog

All notable changes to Semantic Data Portal are documented in this file.

## [Unreleased]

### Added

- Added a governed Measurement Context Registry bounded context for construct,
  criterion, rubric, task, rater-configuration, validation-study, rights, and
  provenance revision metadata.
- Added strict publication and supersession aggregate invariants, referentially
  closed task-to-criterion coverage, bounded collections, and immutable context
  bundles.
- Added an Anti-Corruption Layer that rejects raw responses, observations,
  provider payloads, numerical parameters, scores, adjudication state, and
  product decisions owned by other bounded contexts.
- Added ADR-0001 defining the registry as a policy-filtered Open Host Service
  rather than an assessment or numerical system of record.
