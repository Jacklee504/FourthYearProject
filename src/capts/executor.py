"""Local execution for the first CAPTS GitLab job slice."""

import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

from capts.model import EdgeType, ExecutionResult, PipelineModel, Verdict


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


def execute_gitlab_jobs(
    selected_stage_ids: Iterable[str],
    jobs: Mapping[str, Mapping[str, object]],
    *,
    workspace: str | Path,
    model: PipelineModel | None = None,
) -> list[ExecutionResult]:
    """Execute the selected GitLab jobs in stable order."""
    return [
        execute_gitlab_job(stage_id, jobs[stage_id], workspace=workspace)
        for stage_id in (
            order_execution_stages(model, selected_stage_ids)
            if model is not None
            else sorted(selected_stage_ids)
        )
    ]


def order_execution_stages(
    model: PipelineModel, selected_stage_ids: Iterable[str]
) -> list[str]:
    """Order selected stages by explicit dependencies and triggers."""
    remaining = set(selected_stage_ids)
    dependencies: dict[str, set[str]] = {stage_id: set() for stage_id in remaining}

    for edge in model.edges:
        if (
            edge.edge_type == EdgeType.DEPENDS_ON
            and edge.source in remaining
            and edge.target in remaining
        ):
            dependencies[edge.source].add(edge.target)

    for trigger_job, child_stages in model.triggers.items():
        if trigger_job in remaining:
            for child_stage in child_stages & remaining:
                dependencies[child_stage].add(trigger_job)

    ordered = []
    while remaining:
        ready = min(
            stage_id
            for stage_id in remaining
            if not dependencies[stage_id] & remaining
        )
        ordered.append(ready)
        remaining.remove(ready)
    return ordered


def execution_verdict(results: Iterable[ExecutionResult]) -> Verdict:
    """Return the overall verdict for the supplied stage results."""
    return Verdict.PASS if all(result.passed for result in results) else Verdict.FAIL
