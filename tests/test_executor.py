from capts.executor import execute_gitlab_job, execute_gitlab_jobs


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
