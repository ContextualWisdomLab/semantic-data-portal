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
        raise ValueError(f"unsupported connector vault provider: {provider}")

    secret_ref = connector_secret_ref(connector_id, dataset_id)
    timeout_ms = int(os.getenv("SDP_CONNECTOR_TIMEOUT_MS", "1000"))
    return ConnectorSecretStatus(
        provider=provider,
        secret_ref=secret_ref,
        secret_present=bool(os.getenv(secret_ref)),
        timeout_ms=timeout_ms,
    )
