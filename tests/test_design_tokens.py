"""Design-token system integrity and console regression tests.

These lock in the KRDS-aligned token contract: the operator console must consume
design tokens (never raw hex in component rules), and every token alias must
resolve to a concrete value. See ``src/sdp/design_tokens.py``.
"""

import re

from sdp import design_tokens as dt
from sdp.console import render_enterprise_console


def _style_rules(html: str) -> str:
    """Return the console's CSS rules excluding the :root token-definition block."""
    style = re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)
    return re.sub(r":root \{.*?\}", "", style, count=1, flags=re.DOTALL)


def test_every_token_alias_resolves_to_a_literal():
    flat = dt.flatten()
    # A fully resolved token map must contain no remaining var() references.
    assert flat, "token map is empty"
    assert not any("var(" in value for value in flat.values())


def test_all_three_tiers_are_populated():
    assert dt.PRIMITIVE and dt.SEMANTIC and dt.COMPONENT
    # Semantic/component tiers must only alias other tokens, never inline literals.
    for value in list(dt.SEMANTIC.values()) + list(dt.COMPONENT.values()):
        assert value.startswith("var(--sdp-"), value


def test_semantic_and_component_tokens_reference_defined_tokens():
    names = set(dt.all_tokens())
    for value in list(dt.SEMANTIC.values()) + list(dt.COMPONENT.values()):
        referenced = re.findall(r"var\((--sdp-[a-z0-9-]+)\)", value)
        for ref in referenced:
            assert ref in names, f"{value} references undefined token {ref}"


def test_console_uses_semantic_tokens():
    html = render_enterprise_console()
    assert "--sdp-color-text-primary" in html
    assert "--sdp-color-interaction-primary" in html
    assert "var(--sdp-space-16)" in html
    assert "var(--sdp-radius-surface)" in html


def test_console_component_rules_contain_no_raw_hex():
    # All colours must flow through tokens; raw hex is only allowed inside the
    # :root token definitions, which are excluded here.
    rules = _style_rules(render_enterprise_console())
    assert not re.findall(r"#[0-9a-fA-F]{3,6}", rules)


def test_console_only_references_defined_sdp_tokens():
    html = render_enterprise_console()
    defined = set(dt.all_tokens())
    for ref in re.findall(r"var\((--sdp-[a-z0-9-]+)\)", html):
        assert ref in defined, f"console references undefined token {ref}"


def test_root_block_defines_every_token():
    html = render_enterprise_console()
    root = re.search(r":root \{.*?\}", html, re.DOTALL).group(0)
    for name in dt.all_tokens():
        assert f"{name}:" in root, f"token {name} missing from :root block"


def test_krds_primary_ramp_is_complete_and_anchored():
    flat = dt.flatten()
    steps = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
    for s in steps:
        name = f"--sdp-color-primary-{s}"
        assert name in flat, f"missing {name}"
        assert re.fullmatch(r"#[0-9a-f]{6}", flat[name]), flat[name]
    # 70 must equal the shipping product accent
    assert flat["--sdp-color-primary-70"] == "#0f766e"


def test_krds_space_and_radius_scales():
    flat = dt.flatten()
    for s in (0, 32, 40, 48, 64):
        assert f"--sdp-space-{s}" in flat
    assert flat["--sdp-radius-xs"] == "2px"
    assert flat["--sdp-radius-md"] == "6px"
    assert flat["--sdp-radius-xl"] == "12px"
    assert flat["--sdp-radius-full"] == "999px"


def test_high_contrast_overrides_are_var_only_and_defined():
    names = set(dt.all_tokens())
    for target, value in dt.HIGH_CONTRAST.items():
        assert target in names, f"HC overrides undefined token {target}"
        refs = re.findall(r"var\((--sdp-[a-z0-9-]+)\)", value)
        assert refs, f"HC value must be a var() reference: {value}"
        for ref in refs:
            assert ref in names, f"HC references undefined token {ref}"


def test_high_contrast_css_block_has_no_raw_hex():
    block = dt.high_contrast_css()
    assert '[data-theme="high-contrast"]' in block
    assert not re.findall(r"#[0-9a-fA-F]{3,6}", block)
