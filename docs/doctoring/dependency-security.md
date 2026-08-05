# Dependency security decisions

## Cryptography 50.0.0 security floor

### Decision

All installable Python dependency surfaces must resolve `cryptography==50.0.0` or a later explicitly reviewed replacement. The runtime metadata, test resolver input, and generated hash-locked files are kept aligned so local development, CI, and production installation cannot silently reintroduce an affected release.

### Security rationale

GitHub Advisory Database entry GHSA-g6cj-pr64-35w5 describes a Bleichenbacher-style oracle in PKCS#7 EnvelopedData decryption caused by distinguishable errors and timing. The affected range is `cryptography>=44.0.0,<50.0.0`; version 50.0.0 is the first patched release. The repository previously resolved 49.0.0 through the `PyJWT[crypto]` dependency graph, so the direct security floor is intentional rather than relying on a transitive resolver choice.

### Verification contract

`tests/test_dependency_security.py` verifies that:

1. `pyproject.toml` and `requirements-test.in` declare the patched floor;
2. each installable hash-locked dependency file contains exactly one `cryptography==50.0.0` entry; and
3. no stale affected pin remains in those installation surfaces.

Regenerate the locks with the repository's pinned `uv` compiler and review the resulting graph before merge:

```bash
uv pip compile pyproject.toml --generate-hashes -o requirements.txt
uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements-dev.txt
uv pip compile --generate-hashes --universal --python-version 3.12 \
  requirements-test.in -o requirements-test.txt
```

Security scanning, tests, and exact-current-head review remain required after lock regeneration. A successful scan on an earlier head is not evidence for the regenerated graph.

## Reference

GitHub. (2026, August 3). *Cryptography: PKCS#7 EnvelopedData decryption exposes a Bleichenbacher oracle through distinguishable errors and timing (GHSA-g6cj-pr64-35w5).* GitHub Advisory Database. https://github.com/advisories/GHSA-g6cj-pr64-35w5
