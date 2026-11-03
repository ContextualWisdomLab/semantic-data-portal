from __future__ import annotations

import os
import re
from dataclasses import dataclass


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def connector_secret_ref(connector_id: str, dataset_id: str) -> str:
    prefix = os.getenv("SDP_CONNECTOR_SECRET_REF_PREFIX", "SDP_CONNECTOR_SECRET_")
    return f"{prefix}{_slug(connector_id)}_{_slug(dataset_id)}_TOKEN"


@dataclass(frozen=True)
class ConnectorSecretStatus:
    provider: str
    secret_ref: str
    secret_present: bool
    timeout_ms: int

    def public_dict(self) -> dict[str, object]:
        return {
            "vault_provider": self.provider,
            "secret_ref": self.secret_ref,
            "secret_present": self.secret_present,
            "timeout_ms": self.timeout_ms,
        }


def connector_secret_status(connector_id: str, dataset_id: str) -> ConnectorSecretStatus:
    provider = os.getenv("SDP_CONNECTOR_VAULT_PROVIDER", "env")
    if provider != "env":
        # Names the variable, not just the value. The message read "unsupported
        # connector vault provider: vault" and left the operator to work out
        # which setting held it - and this message is the diagnosis
        # ``sdp.demo_smoke`` now puts in its report instead of raising, so it is
        # the whole of what an operator gets.
        raise ValueError(
            f"unsupported SDP_CONNECTOR_VAULT_PROVIDER: {provider!r} "
            "(only 'env' is implemented)"
        )

    secret_ref = connector_secret_ref(connector_id, dataset_id)
    # Validated, not just parsed. ``timeout_ms`` is published in every rest
    # connector probe's control evidence, so a 0 or negative value is a false
    # published number for a timeout, and int() accepts both. The registry
    # mirrors this domain in ``environment_value_rules`` so the paid-pilot gate
    # refuses a value this function would refuse; the mirror is only honest if
    # the function is the one enforcing it, which is what it does here.
    raw_timeout = os.getenv("SDP_CONNECTOR_TIMEOUT_MS", "1000").strip()
    try:
        timeout_ms = int(raw_timeout)
    except ValueError:
        raise ValueError(
            "SDP_CONNECTOR_TIMEOUT_MS must be an integer number of milliseconds"
        ) from None
    if timeout_ms < 1:
        raise ValueError(
            "SDP_CONNECTOR_TIMEOUT_MS must be at least 1 millisecond"
        )
    return ConnectorSecretStatus(
        provider=provider,
        secret_ref=secret_ref,
        secret_present=bool(os.getenv(secret_ref)),
        timeout_ms=timeout_ms,
    )
