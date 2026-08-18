"""Fail-closed Keyverse tenant binding for the ontology/catalog plane.

SDP consumes an already-issued Keyverse OIDC subject and the
``X-CWL-Tenant-Reference`` header. It does not provision tenants, an IdP, or
SCIM. Missing or mismatched identity is rejected before any catalog object is
read or written.
"""

from __future__ import annotations

import os
from typing import Mapping

from sdp_core.catalog_plane import ACCESS_PURPOSES, AccessPurpose, PlaneActor

from .authz import resolve_actor_context, verify_oidc_jwks_token

TENANT_HEADER = "X-CWL-Tenant-Reference"
SUBJECT_HEADER = "X-CWL-Oidc-Subject"
PURPOSE_HEADER = "X-CWL-Access-Purpose"

_MISSING_IDENTITY_NEXT_ACTION = (
    "Supply a Keyverse OIDC subject (Authorization: Bearer <jwt> or "
    f"{SUBJECT_HEADER}) together with {TENANT_HEADER} and {PURPOSE_HEADER}. "
    "Both identity values must name the same tenant. SDP will not create a "
    "tenant, IdP, or SCIM record for you."
)
_MISMATCH_NEXT_ACTION = (
    f"Correct {TENANT_HEADER} so it matches the Keyverse OIDC tenant claim, "
    "or request access from the tenant that issued the token. SDP does not "
    "re-home subjects across tenants."
)
_PURPOSE_NEXT_ACTION = (
    f"Send {PURPOSE_HEADER} as one of: {', '.join(ACCESS_PURPOSES)}. "
    "Catalog-plane PII (steward name, subject) stays usable for that purpose "
    "and is not masked."
)


class TenantBindingError(Exception):
    """Fail-closed identity error with buyer-facing next-action copy."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str,
        customer_next_action: str,
    ) -> None:
        """Record the HTTP status, stable error code, and next action.

        Parameters
        ----------
        message:
            Operator-readable reason string.
        status_code:
            401 for missing identity, 400 for an unsupported purpose, 403 for
            a tenant mismatch.
        error_code:
            Stable machine-readable code for clients.
        customer_next_action:
            What the buyer should do next.
        """

        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.customer_next_action = customer_next_action


def _header(headers: Mapping[str, str], name: str) -> str:
    """Read a header case-insensitively and strip whitespace."""

    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value).strip()
    return ""


def _purpose_from_headers(headers: Mapping[str, str]) -> AccessPurpose:
    """Require a declared access purpose (purpose limitation, not masking)."""

    purpose = _header(headers, PURPOSE_HEADER)
    if not purpose:
        raise TenantBindingError(
            f"{PURPOSE_HEADER} is required",
            status_code=401,
            error_code="missing_access_purpose",
            customer_next_action=_PURPOSE_NEXT_ACTION,
        )
    if purpose not in ACCESS_PURPOSES:
        raise TenantBindingError(
            f"unsupported {PURPOSE_HEADER}",
            status_code=400,
            error_code="unsupported_access_purpose",
            customer_next_action=_PURPOSE_NEXT_ACTION,
        )
    return purpose  # type: ignore[return-value]


def _actor_from_bearer(authorization: str) -> tuple[str, str, list[str]]:
    """Verify a Bearer JWT with the existing OIDC helper and return identity.

    Raises
    ------
    TenantBindingError
        When the token is missing, malformed, or fails JWKS verification.
    """

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise TenantBindingError(
            "Authorization must be a Bearer token issued by Keyverse",
            status_code=401,
            error_code="invalid_authorization",
            customer_next_action=_MISSING_IDENTITY_NEXT_ACTION,
        )
    try:
        context, _claims = verify_oidc_jwks_token(token.strip())
    except ValueError as exc:
        raise TenantBindingError(
            f"Keyverse OIDC token was rejected: {exc}",
            status_code=401,
            error_code="oidc_token_rejected",
            customer_next_action=(
                "Present a current Keyverse access token, or send "
                f"{SUBJECT_HEADER} from a Keyverse gateway that already "
                "verified the subject. SDP does not operate an IdP."
            ),
        ) from exc
    return context.subject, context.tenant_id, list(context.roles)


def _oidc_verification_required() -> bool:
    """Return whether the existing JWKS verifier is configured.

    Issuer, audience, and JWKS URL are the same transport coordinates already
    used by :func:`verify_oidc_jwks_token`. When they are present, the plane
    rejects ``X-CWL-Oidc-Subject`` so a client cannot self-assert ``admin``.
    """

    return bool(
        os.getenv("SDP_OIDC_ISSUER")
        and os.getenv("SDP_OIDC_AUDIENCE")
        and os.getenv("SDP_OIDC_JWKS_URL")
    )


def _actor_from_subject_header(subject: str) -> tuple[str, str, list[str]]:
    """Resolve a demo-map subject only when JWKS verification is not configured."""

    if _oidc_verification_required():
        raise TenantBindingError(
            "X-CWL-Oidc-Subject is not accepted when Keyverse JWKS is configured",
            status_code=401,
            error_code="oidc_subject_header_rejected",
            customer_next_action=(
                "Send Authorization: Bearer <Keyverse access token>. "
                "SDP consumes the verified OIDC subject and does not treat a "
                "raw subject header as authentication when JWKS is configured."
            ),
        )
    context = resolve_actor_context(subject)
    if not context.tenant_id or not context.roles:
        raise TenantBindingError(
            "Keyverse OIDC subject is not bound to a tenant",
            status_code=401,
            error_code="unbound_oidc_subject",
            customer_next_action=_MISSING_IDENTITY_NEXT_ACTION,
        )
    return context.subject, context.tenant_id, list(context.roles)


def bind_keyverse_tenant(headers: Mapping[str, str]) -> PlaneActor:
    """Bind the request to one tenant or fail closed.

    Identity sources, in order:

    1. ``Authorization: Bearer`` — verified with the existing JWKS helper.
    2. ``X-CWL-Oidc-Subject`` — demo/CI actor map only, and only when JWKS
       verification is **not** configured. Production with Keyverse JWKS must
       send a Bearer token.

    The ``X-CWL-Tenant-Reference`` header must match the OIDC tenant claim.
    Platform-admin is not a cross-tenant escape hatch on this plane.

    Parameters
    ----------
    headers:
        Incoming HTTP headers.

    Returns
    -------
    PlaneActor
        Subject, tenant, roles, and declared purpose.

    Raises
    ------
    TenantBindingError
        On missing, malformed, or mismatched identity.
    """

    tenant_reference = _header(headers, TENANT_HEADER)
    if not tenant_reference:
        raise TenantBindingError(
            f"{TENANT_HEADER} is required",
            status_code=401,
            error_code="missing_tenant_reference",
            customer_next_action=_MISSING_IDENTITY_NEXT_ACTION,
        )

    purpose = _purpose_from_headers(headers)
    authorization = _header(headers, "Authorization")
    subject_header = _header(headers, SUBJECT_HEADER)

    if authorization:
        subject, tenant_id, roles = _actor_from_bearer(authorization)
        binding_source = "oidc_bearer"
    elif subject_header:
        subject, tenant_id, roles = _actor_from_subject_header(subject_header)
        binding_source = "oidc_subject_header"
    else:
        raise TenantBindingError(
            "Keyverse OIDC subject is required",
            status_code=401,
            error_code="missing_oidc_subject",
            customer_next_action=_MISSING_IDENTITY_NEXT_ACTION,
        )

    if tenant_id != tenant_reference:
        raise TenantBindingError(
            "X-CWL-Tenant-Reference does not match the Keyverse OIDC tenant",
            status_code=403,
            error_code="tenant_reference_mismatch",
            customer_next_action=_MISMATCH_NEXT_ACTION,
        )

    return PlaneActor(
        subject=subject,
        tenant_reference=tenant_reference,
        roles=roles,
        access_purpose=purpose,
        binding_source=binding_source,
    )
