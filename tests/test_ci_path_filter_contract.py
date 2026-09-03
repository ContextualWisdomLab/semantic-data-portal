"""Contracts for documentation-only workflow filtering."""

from pathlib import Path


def _event_block(workflow: str, event: str) -> str:
    """Return one top-level event block from the workflow's ``on`` mapping."""
    lines = workflow.splitlines()
    marker = f"  {event}:"
    try:
        start = lines.index(marker)
    except ValueError as exc:
        raise AssertionError(f"missing workflow event: {event}") from exc

    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        block.append(line)
    return "\n".join(block)


def test_fuzz_workflow_ignores_documentation_per_code_change_trigger() -> None:
    """Push and PR triggers independently skip docs and nested Markdown changes."""
    workflow = Path(".github/workflows/fuzz.yml").read_text(encoding="utf-8")

    for event in ("push", "pull_request"):
        block = _event_block(workflow, event)
        assert '      - "docs/**"' in block
        assert '      - "**.md"' in block
        assert '      - "*.md"' not in block
