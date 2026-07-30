"""JWKS loader scheme-validation guard (SSRF/LFI hardening)."""

import pytest

from sdp.authz import _load_jwks_from_url


@pytest.mark.parametrize(
    "jwks_url",
    ["file:///etc/passwd", "ftp://example.com/keys", "data:text/plain,{}", ""],
)
def test_load_jwks_rejects_non_network_schemes(jwks_url):
    """A misconfigured JWKS URL must not let urllib read local files or other
    non-network resources — only http/https are accepted, so the scheme is
    rejected before urlopen is ever reached."""
    with pytest.raises(ValueError, match="unsupported SDP_OIDC_JWKS_URL scheme"):
        _load_jwks_from_url(jwks_url)
