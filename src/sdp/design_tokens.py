"""Single source of truth for Semantic Data Portal design tokens.

This module encodes the KRDS-aligned design system that is authored visually in
Figma (file ``JjYSqr6nWxpARUjaVKhG16``) as machine-usable CSS custom properties so
that the operator console and any future front-end consume the *same* tokens the
design system defines, instead of ad-hoc hex/px literals.

Token tiers (KRDS / spec section 4)
-----------------------------------
1. ``primitive`` -- raw, context-free values (``--sdp-color-gray-900``, ``--sdp-space-16``).
2. ``semantic``  -- meaning-based aliases of primitives (``--sdp-color-text-primary``).
3. ``component`` -- component-scoped aliases of semantics (``--sdp-badge-success-fg``).

Figma / code split
-------------------
Figma owns the *primitive* and *semantic* tiers (as Figma Variables). Code owns the
*component* tier, because component values are consumed by the rendered surface. The
CSS variable names mirror the Figma variable names (dots become dashes, ``sdp`` prefix),
e.g. Figma ``color/text/primary`` <-> CSS ``--sdp-color-text-primary``. Figma Code
Connect is intentionally not used (see ``docs/enterprise-readiness.md``).

Values here are the exact colours/metrics that shipped in the operator console, so
adopting the token layer is a non-breaking refactor (every ``var()`` resolves to the
value it replaced). :func:`flatten` proves this by expanding every alias to a literal.
"""

from __future__ import annotations

from collections import OrderedDict

# --- Tier 1: primitive tokens (raw values) ---------------------------------
PRIMITIVE: "OrderedDict[str, str]" = OrderedDict(
    [
        # neutral ramp
        ("--sdp-color-white", "#ffffff"),
        ("--sdp-color-gray-50", "#f7f9fc"),
        ("--sdp-color-gray-75", "#eef3f8"),
        ("--sdp-color-gray-100", "#eef2f6"),
        ("--sdp-color-gray-150", "#dce5ee"),
        ("--sdp-color-gray-200", "#d8dee8"),
        ("--sdp-color-gray-500", "#5b6778"),
        ("--sdp-color-gray-900", "#17202a"),
        # brand ramp (teal)
        ("--sdp-color-teal-700", "#0f766e"),
        # status: success (green)
        ("--sdp-color-green-50", "#eff8f0"),
        ("--sdp-color-green-200", "#bbd7c0"),
        ("--sdp-color-green-600", "#166534"),
        # status: warning (amber)
        ("--sdp-color-amber-50", "#fff8e7"),
        ("--sdp-color-amber-200", "#e7cf96"),
        ("--sdp-color-amber-700", "#a16207"),
        # spacing scale (px). NOTE: 3/9/18 are legacy off-4px-grid values kept to
        # preserve the shipped layout; flagged for normalisation in docs/design-tokens.md.
        ("--sdp-space-2", "2px"),
        ("--sdp-space-3", "3px"),
        ("--sdp-space-4", "4px"),
        ("--sdp-space-6", "6px"),
        ("--sdp-space-8", "8px"),
        ("--sdp-space-9", "9px"),
        ("--sdp-space-10", "10px"),
        ("--sdp-space-12", "12px"),
        ("--sdp-space-14", "14px"),
        ("--sdp-space-16", "16px"),
        ("--sdp-space-18", "18px"),
        ("--sdp-space-20", "20px"),
        ("--sdp-space-24", "24px"),
        ("--sdp-space-28", "28px"),
        # radius scale
        ("--sdp-radius-6", "6px"),
        ("--sdp-radius-8", "8px"),
        ("--sdp-radius-pill", "999px"),
        # type scale
        ("--sdp-font-size-11", "11px"),
        ("--sdp-font-size-12", "12px"),
        ("--sdp-font-size-13", "13px"),
        ("--sdp-font-size-14", "14px"),
        ("--sdp-font-size-15", "15px"),
        ("--sdp-font-size-22", "22px"),
        ("--sdp-font-size-24", "24px"),
        ("--sdp-font-weight-medium", "650"),
        ("--sdp-font-weight-bold", "700"),
        ("--sdp-font-weight-heavy", "750"),
        ("--sdp-line-height-normal", "1.5"),
    ]
)

# --- Tier 2: semantic tokens (alias primitives) ----------------------------
SEMANTIC: "OrderedDict[str, str]" = OrderedDict(
    [
        ("--sdp-color-text-primary", "var(--sdp-color-gray-900)"),
        ("--sdp-color-text-muted", "var(--sdp-color-gray-500)"),
        ("--sdp-color-surface-default", "var(--sdp-color-white)"),
        ("--sdp-color-surface-muted", "var(--sdp-color-gray-50)"),
        ("--sdp-color-surface-strong", "var(--sdp-color-gray-75)"),
        ("--sdp-color-background-canvas", "var(--sdp-color-gray-100)"),
        ("--sdp-color-border-default", "var(--sdp-color-gray-200)"),
        ("--sdp-color-border-muted", "var(--sdp-color-gray-150)"),
        ("--sdp-color-interaction-primary", "var(--sdp-color-teal-700)"),
        ("--sdp-color-focus-ring", "var(--sdp-color-teal-700)"),
        ("--sdp-color-status-success-fg", "var(--sdp-color-green-600)"),
        ("--sdp-color-status-success-border", "var(--sdp-color-green-200)"),
        ("--sdp-color-status-success-bg", "var(--sdp-color-green-50)"),
        ("--sdp-color-status-warning-fg", "var(--sdp-color-amber-700)"),
        ("--sdp-color-status-warning-border", "var(--sdp-color-amber-200)"),
        ("--sdp-color-status-warning-bg", "var(--sdp-color-amber-50)"),
        ("--sdp-radius-control", "var(--sdp-radius-6)"),
        ("--sdp-radius-surface", "var(--sdp-radius-8)"),
        ("--sdp-radius-track", "var(--sdp-radius-pill)"),
    ]
)

# --- Tier 3: component tokens (alias semantics) ----------------------------
COMPONENT: "OrderedDict[str, str]" = OrderedDict(
    [
        ("--sdp-badge-success-fg", "var(--sdp-color-status-success-fg)"),
        ("--sdp-badge-success-border", "var(--sdp-color-status-success-border)"),
        ("--sdp-badge-success-bg", "var(--sdp-color-status-success-bg)"),
        ("--sdp-badge-warning-fg", "var(--sdp-color-status-warning-fg)"),
        ("--sdp-badge-warning-border", "var(--sdp-color-status-warning-border)"),
        ("--sdp-badge-warning-bg", "var(--sdp-color-status-warning-bg)"),
    ]
)

_TIERS = (("primitive", PRIMITIVE), ("semantic", SEMANTIC), ("component", COMPONENT))


def all_tokens() -> "OrderedDict[str, str]":
    """Return every token as ``name -> authored value`` (primitives literal, others ``var(...)``)."""
    merged: "OrderedDict[str, str]" = OrderedDict()
    for _, tier in _TIERS:
        merged.update(tier)
    return merged


def resolve(value: str, _tokens: "OrderedDict[str, str] | None" = None) -> str:
    """Recursively expand any ``var(--token)`` references in *value* to a literal.

    Raises ``KeyError`` if a referenced token is undefined (guards against typos).
    """
    tokens = _tokens if _tokens is not None else all_tokens()
    seen = 0
    while "var(" in value:
        start = value.index("var(")
        end = value.index(")", start)
        name = value[start + len("var(") : end].strip()
        if name not in tokens:
            raise KeyError(f"undefined design token: {name}")
        value = value[:start] + tokens[name] + value[end + 1 :]
        seen += 1
        if seen > 100:  # pragma: no cover - defensive against cyclic aliases
            raise RuntimeError(f"cyclic design token reference near: {value!r}")
    return value


def flatten() -> "OrderedDict[str, str]":
    """Return ``name -> fully-resolved literal`` for every token (proves alias integrity)."""
    tokens = all_tokens()
    return OrderedDict((name, resolve(authored, tokens)) for name, authored in tokens.items())


def root_css_variables(indent: str = "      ") -> str:
    """Render the ``:root { ... }`` declaration block that defines every token.

    Grouped and commented by tier so the generated CSS stays legible in view-source.
    """
    lines = [":root {", f"{indent}color-scheme: light;"]
    headings = {
        "primitive": "/* tier 1: primitive tokens */",
        "semantic": "/* tier 2: semantic tokens */",
        "component": "/* tier 3: component tokens */",
    }
    for tier_name, tier in _TIERS:
        lines.append(f"{indent}{headings[tier_name]}")
        for name, value in tier.items():
            lines.append(f"{indent}{name}: {value};")
    lines.append("    }")
    return "\n".join(lines)
