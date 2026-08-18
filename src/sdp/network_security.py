"""Security boundaries for configuration-driven outbound HTTP requests.

The service accepts a small number of operator-configured callback URLs.  This
module centralizes their syntactic validation so callers cannot accidentally
pass local-file, loopback, link-local, or other non-public destinations to a
network client.  Runtime egress controls remain the second line of defense
against DNS rebinding and infrastructure-specific private address ranges.
"""

from __future__ import annotations

from ipaddress import ip_address
from socket import inet_aton
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirects(HTTPRedirectHandler):
    """Reject redirect responses before urllib can issue a follow-up request."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        """Reject the follow-up URL instead of letting urllib request it."""

        del req, fp, code, msg, headers
        raise ValueError(f"outbound HTTPS redirect rejected: {newurl}")


def open_url_without_redirects(
    request: str | Request,
    *,
    timeout: float,
) -> Any:
    """Open one already-validated URL while refusing every redirect hop."""

    opener = build_opener(_RejectRedirects())
    return opener.open(request, timeout=timeout)  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- callers validate the initial public HTTPS URL and redirects are rejected here


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
        legacy_ipv4 = ip_address(inet_aton(normalized_host))
    except (OSError, UnicodeError):
        legacy_ipv4 = None

    if legacy_ipv4 is not None:
        if not legacy_ipv4.is_global:
            raise ValueError(f"{setting_name} must target a global IP address")
        ascii_host = str(legacy_ipv4)
    else:
        try:
            address = ip_address(normalized_host)
        except ValueError:
            try:
                ascii_host = normalized_host.encode("idna").decode("ascii")
            except UnicodeError as exc:
                raise ValueError(f"{setting_name} contains an invalid hostname") from exc
            try:
                idna_address = ip_address(ascii_host)
            except ValueError:
                try:
                    idna_address = ip_address(inet_aton(ascii_host))
                except OSError:
                    idna_address = None
            if idna_address is not None:
                if not idna_address.is_global:
                    raise ValueError(
                        f"{setting_name} must target a global IP address"
                    ) from None
                ascii_host = str(idna_address)
            elif (
                ascii_host == "localhost"
                or ascii_host.endswith(".localhost")
                or "." not in ascii_host
            ):
                raise ValueError(
                    f"{setting_name} must target a public DNS hostname"
                ) from None
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
