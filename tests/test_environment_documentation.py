"""Every environment variable this service reads must be findable in the operator docs.

``CLAUDE.md`` opens its environment section with "모두 ``SDP_`` prefix" and then lists them, and
``README.md`` describes them in prose. Both present themselves as enumerations, and both were
incomplete. Measured over ``src/``, 9 of the 23 ``SDP_`` names appearing there were missing from one
document or both:

    SDP_CONNECTOR_TIMEOUT_MS         required_environment, in neither document
    SDP_CONNECTOR_VAULT_PROVIDER     required_environment, in neither document
    SDP_ALERT_TIMEOUT_MS             in CLAUDE.md only
    SDP_DATABASE_DSN                 in README.md only
    SDP_CONFIG_NAMESPACE             in neither
    SDP_ENV                          in neither
    SDP_OIDC_JWKS_TIMEOUT_SECONDS    in neither
    SDP_OIDC_JWKS_TTL_SECONDS        in neither
    SDP_EVIDENCE_RETENTION_DAYS      declared-unimplemented, in neither

The first two are the ones that matter most, and they are not a documentation nicety.
``production_integration_registry`` lists both in ``connector_credential_vault``'s
``required_environment``, so ``GET /enterprise/production-readiness`` names them in
``missing_environment`` and withholds ``paid_pilot_ready`` until they are set - while no operator
document said they existed, what they selected, or what to set them to. A readiness gate an
operator cannot act on is worse than no gate: it reports a blocker and hides the remedy.

The set is **derived from the source**, never listed here. A hand-written inventory is the shape
this repository keeps finding at fault - a guard compared against its own list rather than against
the thing it describes - and an inventory of environment variables goes stale on exactly the commit
that adds one, which is the commit nobody is looking at it.

Two directions are checked, because each catches a different defect:

* read but undocumented - an operator cannot discover a knob that changes behaviour;
* documented but unread - a document promising a variable that does nothing, which is what
  ``declared_unimplemented_environment`` exists to make honest. A name may be documented and unread
  only while the registry declares it unimplemented.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp_core.production import production_integration_registry  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"

# The two documents that enumerate configuration for a reader: the operator-facing README and the
# agent-facing guide. Both are checked, because a reader of either should be able to find every
# knob, and each has drifted independently.
OPERATOR_DOCS = ("README.md", "CLAUDE.md")

# ``credentials.py`` builds per-connector names from this prefix, so the literal in the source is
# not itself a variable. It is documented as ``SDP_CONNECTOR_SECRET_*``, and the matcher below
# accepts that form, so this needs no exception - it is named here only so a reader of a failure
# knows why a trailing-underscore literal is in the set at all.
_NAME_LITERAL = re.compile(r'["\'](SDP_[A-Z0-9_]+)["\']')

# The declaration site is excluded from "is it read": listing a name in the registry is the
# declaration, not a consumer. This mirrors
# ``tests/test_production_readiness_measurement.py::_consumers``.
_DECLARATION_FILE = "production.py"


def _names_in_source() -> dict[str, list[str]]:
    """Every ``SDP_`` name appearing in ``src/``, mapped to the files it appears in.

    Matched on string literals rather than on ``os.getenv`` calls: the variables are reached
    several ways here - ``os.getenv``, ``os.environ.get``, ``os.environ[...]``, and a name passed
    into a settings loader - and a check that recognised only one call shape would report a
    documented-and-read variable as unread. Measured, the ``os.getenv``-only form found 18 of the
    23 names.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _NAME_LITERAL.finditer(text):
            found.setdefault(match.group(1), []).append(
                path.relative_to(SOURCE_ROOT).as_posix()
            )
    assert found, "no SDP_ names were found in src/; re-point this test"
    return found


def _documented(name: str, text: str) -> bool:
    """Whether a document names this variable, allowing a documented wildcard family.

    ``SDP_CONNECTOR_SECRET_`` is a prefix the source concatenates onto; the docs write the family
    as ``SDP_CONNECTOR_SECRET_*``. Accepting the wildcard is what lets the set stay derived from
    the source instead of carrying an exception list.
    """
    if name in text:
        return True
    return name.endswith("_") and f"{name}*" in text


def _registry_environment() -> tuple[set[str], set[str]]:
    """The names the readiness registry requires, and the ones it declares unimplemented."""
    required: set[str] = set()
    declared: set[str] = set()
    for item in production_integration_registry():
        required |= set(item.required_environment)
        for group in item.required_environment_alternatives:
            required |= set(group)
        declared |= set(item.declared_unimplemented_environment)
    return required, declared


def test_every_variable_the_source_reads_is_in_both_operator_documents() -> None:
    """Read but undocumented: a knob an operator cannot find."""
    in_source = _names_in_source()
    texts = {
        name: (REPO_ROOT / name).read_text(encoding="utf-8") for name in OPERATOR_DOCS
    }

    undocumented: dict[str, list[str]] = {}
    for variable, files in sorted(in_source.items()):
        missing = [doc for doc, text in texts.items() if not _documented(variable, text)]
        if missing:
            undocumented[variable] = missing

    assert undocumented == {}, (
        "these variables change this service's behaviour and are absent from the "
        f"operator documents named: {undocumented}. Each is read in "
        f"{ {v: sorted(set(in_source[v])) for v in undocumented} }."
    )


def test_every_variable_the_readiness_gate_requires_is_documented() -> None:
    """The buyer-blocking half, asserted on its own so a failure says which half broke.

    ``GET /enterprise/production-readiness`` withholds ``paid_pilot_ready`` until every
    ``required_environment`` name is set and reports the missing ones. An operator who reads that
    response and then cannot find the variable in any document has a blocker with no remedy -
    measured, ``SDP_CONNECTOR_TIMEOUT_MS`` and ``SDP_CONNECTOR_VAULT_PROVIDER`` were in exactly
    that state.
    """
    required, _ = _registry_environment()
    texts = {
        name: (REPO_ROOT / name).read_text(encoding="utf-8") for name in OPERATOR_DOCS
    }
    missing = {
        variable: [doc for doc, text in texts.items() if not _documented(variable, text)]
        for variable in sorted(required)
    }
    missing = {variable: docs for variable, docs in missing.items() if docs}
    assert missing == {}, (
        "the readiness gate requires these variables and no operator document says what they "
        f"are, so the published blocker cannot be acted on: {missing}"
    )


def test_no_document_promises_a_variable_nothing_reads() -> None:
    """Documented but unread - unless the registry declares it unimplemented.

    The other direction, and the one ``declared_unimplemented_environment`` exists for: a document
    naming a variable no code consumes tells an operator a capability is configurable when it is
    not. ``SDP_EVIDENCE_RETENTION_DAYS`` is the accepted case - it is documented *as*
    declared-unimplemented, and the registry publishes that through
    ``unimplemented_environment``.
    """
    in_source = _names_in_source()
    _, declared = _registry_environment()
    readable = set(in_source) | declared

    phantom: dict[str, list[str]] = {}
    for doc in OPERATOR_DOCS:
        text = (REPO_ROOT / doc).read_text(encoding="utf-8")
        for variable in sorted(set(_NAME_LITERAL.findall(text)) | set(re.findall(r"`(SDP_[A-Z0-9_]+)`", text))):
            if variable in readable:
                continue
            if any(variable.startswith(f"{known}") for known in readable if known.endswith("_")):
                continue
            phantom.setdefault(variable, []).append(doc)

    assert phantom == {}, (
        "these documents name variables nothing in src/ reads and the registry does not declare "
        f"unimplemented: {phantom}. Either wire them or declare them; a document that promises a "
        "no-op variable is the defect declared_unimplemented_environment exists to prevent."
    )
