from capts.executor import execute_gitlab_job


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
