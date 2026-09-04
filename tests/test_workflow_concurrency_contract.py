from pathlib import Path


WORKFLOWS = Path(".github/workflows")
PR_GROUP = "${{ github.workflow }}-${{ github.repository }}-${{ github.event.pull_request.number || github.run_id }}"
PR_CANCEL = "${{ github.event_name == 'pull_request' }}"


def test_pr_workflows_cancel_only_superseded_heads() -> None:
    for name in ("tests.yml", "fuzz.yml"):
        workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert f"group: {PR_GROUP}" in workflow
        assert f"cancel-in-progress: {PR_CANCEL}" in workflow


def test_scorecard_delegates_without_cancelling_release_evidence() -> None:
    workflow = (WORKFLOWS / "scorecard-analysis.yml").read_text(encoding="utf-8")
    assert "uses: ContextualWisdomLab/.github/.github/workflows/scorecard-analysis.yml@" in workflow
    assert "cancel-in-progress: true" not in workflow


def test_fuzz_skips_documentation_only_changes() -> None:
    workflow = (WORKFLOWS / "fuzz.yml").read_text(encoding="utf-8")
    assert workflow.count('      - "docs/**"') == 2
    assert workflow.count('      - "**.md"') == 2
