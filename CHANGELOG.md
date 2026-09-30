# Changelog

## Unreleased

### Security

- Complete the dependency-lock repair across runtime, development, test, and graph install surfaces by upgrading PyJWT to 2.14.0 and constraining the graph lock to the patched AnyIO and cryptography releases.
- Upgrade pypdf to 6.16.1 and carry the patched document-parser dependency through every hash-locked install surface.
