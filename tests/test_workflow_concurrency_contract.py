"""Queue-bounding contracts for pull-request workflows."""

from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PR_LIFECYCLE = (
    "types: [opened, synchronize, reopened, ready_for_review, converted_to_draft, closed]"
)
PR_GROUP = (
    "group: ${{ github.workflow }}-${{ github.repository }}-"
    "${{ github.event_name == 'pull_request' && github.event.pull_request.number || github.run_id }}"
)
PR_CANCEL = "cancel-in-progress: ${{ github.event_name == 'pull_request' }}"
PR_ADMISSION = (
    "if: ${{ github.event_name != 'pull_request' || "
    "(github.event.action != 'closed' && github.event.pull_request.draft == false) }}"
)


def test_pull_request_workflows_isolate_current_reviewable_heads() -> None:
    expected_jobs = {"fuzz.yml": 2, "tests.yml": 1}

    for name, job_count in expected_jobs.items():
        workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert PR_LIFECYCLE in workflow
        assert PR_GROUP in workflow
        assert PR_CANCEL in workflow
        assert workflow.count(PR_ADMISSION) == job_count
