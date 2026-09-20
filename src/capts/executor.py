"""Local execution for the first CAPTS GitLab job slice."""

import subprocess
from collections.abc import Mapping
from pathlib import Path

from capts.model import ExecutionResult


def execute_gitlab_job(
    stage_id: str,
    job: Mapping[str, object],
    *,
    workspace: str | Path,
) -> ExecutionResult:
    """Execute one GitLab job script from the supplied workspace."""
    script = job.get("script")
    if isinstance(script, str):
        script = [script]
    if not isinstance(script, list) or not all(isinstance(line, str) for line in script):
        raise ValueError("GitLab job script must be a string or list of strings.")

    completed = subprocess.run(
        "\n".join(script),
        shell=True,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return ExecutionResult(
        stage_id=stage_id,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
