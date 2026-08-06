"""Security boundaries for configuration-driven outbound HTTP requests.

The service accepts a small number of operator-configured callback URLs.  This
module centralizes their syntactic validation so callers cannot accidentally
pass local-file, loopback, link-local, or other non-public destinations to a
network client.  Runtime egress controls remain the second line of defense
against DNS rebinding and infrastructure-specific private address ranges.
"""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit


def validate_outbound_https_url(raw_url: str, *, setting_name: str) -> str:
    """Return a normalized public HTTPS URL or raise :class:`ValueError`.

    Args:
        raw_url: Operator-provided URL to validate.
        setting_name: Human-readable configuration key used in error messages.

    Returns:
        A normalized HTTPS URL with an explicit path.

    Raises:
        ValueError: If the URL is empty, malformed, contains credentials or a
            fragment, uses a non-HTTPS scheme, targets a local/single-label
            hostname, or contains a non-global IP literal.

    Notes:
        DNS names are deliberately not resolved here.  Resolution at validation
        time creates a time-of-check/time-of-use gap; deployments must also use
        an outbound proxy, firewall, or equivalent egress policy that blocks
        private and metadata-service address ranges after DNS resolution.
    """

    candidate = raw_url.strip()
    if not candidate:
        raise ValueError(f"{setting_name} must not be empty")

    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise ValueError(f"{setting_name} must be a valid URL") from exc

    if parsed.scheme.lower() != "https":
        raise ValueError(f"{setting_name} must use https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{setting_name} must not contain URL credentials")
    if parsed.fragment:
        raise ValueError(f"{setting_name} must not contain a fragment")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"{setting_name} must include a hostname")
    normalized_host = hostname.rstrip(".").lower()
    if not normalized_host:
        raise ValueError(f"{setting_name} must include a hostname")

    try:
        address = ip_address(normalized_host)
    except ValueError:
        try:
            ascii_host = normalized_host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"{setting_name} contains an invalid hostname") from exc
        if (
            ascii_host == "localhost"
            or ascii_host.endswith(".localhost")
            or "." not in ascii_host
        ):
            raise ValueError(f"{setting_name} must target a public DNS hostname")
    else:
        if not address.is_global:
            raise ValueError(f"{setting_name} must target a global IP address")
        ascii_host = normalized_host

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{setting_name} contains an invalid port") from exc

    authority = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    if port is not None:
        authority = f"{authority}:{port}"

    return urlunsplit(("https", authority, parsed.path or "/", parsed.query, ""))
