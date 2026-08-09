# Changelog

All notable changes to Semantic Data Portal are documented in this file.

## [Unreleased]

### Fixed

- Removed hard-coded customer, RDF, file-lake, and REST preview rows from production source paths. Catalog/schema metadata remains available, while data-plane preview fails closed with `source_preview_backend_not_configured` until a provider-backed executor exists.

### Security

- Preview policy evaluation remains authoritative before the unavailable result; catalog metadata is no longer reclassified as source data, and source adapters no longer emit synthetic records that could be mistaken for tenant data.
