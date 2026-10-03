"""Require isolated self-hosted execution for every product CI job."""
from pathlib import Path
import re


def test_product_ci_has_no_hosted_or_privileged_runner() -> None:
    """Check all four existing declarations without executing workflow steps."""
    declarations = []
    for path in sorted(Path('.github/workflows').glob('*.yml')):
        for line in path.read_text().splitlines():
            if re.match(r'^    runs-on:', line):
                declarations.append((path, line.strip()))
    assert len(declarations) == 4
    assert all(line == 'runs-on: [self-hosted, linux, x64, cwlab-ci-isolated]' for _, line in declarations)
