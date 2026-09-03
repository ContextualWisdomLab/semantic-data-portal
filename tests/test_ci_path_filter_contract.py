"""Contracts for documentation-only workflow filtering."""

from pathlib import Path


def test_fuzz_workflow_ignores_markdown_at_any_depth() -> None:
    """The optional fuzz lane skips Markdown-only changes at any repository depth."""
    workflow = Path(".github/workflows/fuzz.yml").read_text(encoding="utf-8")

    assert workflow.count('      - "**.md"') == 2
    assert '      - "*.md"' not in workflow
