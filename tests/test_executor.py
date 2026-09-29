import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from capts.executor import (
    execute_gitlab_job,
    execute_gitlab_jobs,
    execution_verdict,
    order_execution_stages,
)
from capts.model import EdgeInfo, EdgeType, ExecutionResult, PipelineModel, Verdict

ECOSYSTEM = Path(__file__).parent / "fixtures" / "ecosystem"


def test_execute_gitlab_job_returns_a_passing_result(tmp_path) -> None:
    (tmp_path / "child").mkdir()

    result = execute_gitlab_job(
        "main/build",
        {"script": ["cd child", "pwd"]},
        workspace=tmp_path,
    )

    assert result.stage_id == "main/build"
    assert result.exit_code == 0
    assert result.passed
    assert result.stdout == f"{(tmp_path / 'child').resolve()}\n"
    assert result.stderr == ""


def test_execute_gitlab_job_returns_a_failing_result(tmp_path) -> None:
    result = execute_gitlab_job(
        "main/security-scan",
        {"script": "printf 'scan failed\\n' >&2; exit 1"},
        workspace=tmp_path,
    )

    assert result.stage_id == "main/security-scan"
    assert result.exit_code == 1
    assert not result.passed
    assert result.stdout == ""
    assert result.stderr == "scan failed\n"


def test_execute_gitlab_jobs_runs_selected_jobs_in_stable_order(tmp_path) -> None:
    results = execute_gitlab_jobs(
        {"main/test", "main/build"},
        {
            "main/build": {"script": "printf build"},
            "main/test": {"script": "printf test"},
            "main/deploy": {"script": "exit 1"},
        },
        workspace=tmp_path,
        model=PipelineModel(),
    )

    assert [(result.stage_id, result.stdout, result.passed) for result in results] == [
        ("main/build", "build", True),
        ("main/test", "test", True),
    ]


def test_execute_gitlab_jobs_keeps_failed_results(tmp_path) -> None:
    results = execute_gitlab_jobs(
        {"main/build", "main/test"},
        {
            "main/build": {"script": "exit 1"},
            "main/test": {"script": "exit 0"},
        },
        workspace=tmp_path,
    )

    assert [(result.stage_id, result.passed) for result in results] == [
        ("main/build", False),
        ("main/test", True),
    ]


def test_execute_gitlab_jobs_returns_no_results_without_selected_stages(tmp_path) -> None:
    results = execute_gitlab_jobs(
        [],
        {"main/build": {"script": "exit 1"}},
        workspace=tmp_path,
    )

    assert results == []


def test_execute_gitlab_jobs_respects_explicit_dependency_order(tmp_path) -> None:
    results = execute_gitlab_jobs(
        {"main/build", "main/test"},
        {
            "main/build": {"script": "printf build"},
            "main/test": {"script": "printf test"},
        },
        workspace=tmp_path,
        model=PipelineModel(
            edges=[EdgeInfo("main/test", "main/build", EdgeType.DEPENDS_ON)]
        ),
    )

    assert [result.stage_id for result in results] == ["main/build", "main/test"]


def test_execute_gitlab_jobs_runs_trigger_before_selected_child(tmp_path) -> None:
    results = execute_gitlab_jobs(
        {"main/gate", "deploy/build"},
        {
            "main/gate": {"script": "printf gate"},
            "deploy/build": {"script": "printf deploy"},
        },
        workspace=tmp_path,
        model=PipelineModel(triggers={"main/gate": {"deploy/build"}}),
    )

    assert [result.stage_id for result in results] == ["main/gate", "deploy/build"]


def test_execution_order_does_not_add_unselected_stages() -> None:
    model = PipelineModel(
        edges=[EdgeInfo("main/test", "main/build", EdgeType.DEPENDS_ON)],
        triggers={"main/gate": {"deploy/build"}},
    )

    assert order_execution_stages(model, {"main/build"}) == ["main/build"]


def test_execution_verdict_passes_when_all_stages_pass() -> None:
    results = [
        ExecutionResult("main/build", 0),
        ExecutionResult("main/test", 0),
    ]

    assert execution_verdict(results) == Verdict.PASS


def test_execution_verdict_fails_when_one_stage_fails() -> None:
    results = [
        ExecutionResult("main/build", 0),
        ExecutionResult("main/test", 1),
    ]

    assert execution_verdict(results) == Verdict.FAIL


def test_execution_verdict_passes_without_selected_stages() -> None:
    assert execution_verdict([]) == Verdict.PASS


@pytest.mark.parametrize(
    ("script", "options"),
    [
        ("build.py", ("--registry", "REGISTRY_URL", "--cmd", "BUILD_CMD")),
        ("test_runner.py", ("--flags", "FEATURE_FLAGS")),
        ("scan.py", ("--threshold", "SCAN_THRESHOLD")),
        ("deploy.py", ("--registry", "REGISTRY_URL", "--strategy", "DEPLOY_STRATEGY")),
        ("deploy.py", ("--registry", "REGISTRY_URL")),
        ("notify.py", ("--channel", "NOTIFICATION_CHANNEL")),
    ],
)
def test_base_ecosystem_script_succeeds(script: str, options: tuple[str, ...]) -> None:
    with (ECOSYSTEM / "main.yml").open(encoding="utf-8") as source:
        variables = yaml.safe_load(source)["variables"]
    arguments = [variables.get(option, option) for option in options]

    result = subprocess.run(
        [sys.executable, str(ECOSYSTEM / "scripts" / script), *arguments],
        cwd=ECOSYSTEM,
        env={**os.environ, **variables},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
