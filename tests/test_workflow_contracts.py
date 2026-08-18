"""Machine-checkable contracts for required GitHub status contexts."""

from pathlib import Path


def test_api_integration_status_depends_on_full_suite() -> None:
    """Keep the legacy protected-branch context tied to the complete test gate."""
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")

    assert "api_integration_suite:" in workflow
    assert "name: API integration suite" in workflow
    assert "needs: pytest" in workflow
