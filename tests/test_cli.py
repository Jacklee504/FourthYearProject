from pathlib import Path

from capts.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_selects_stages_through_the_gitlab_adapter(capsys) -> None:
    status = main(
        [
            str(FIXTURES / "m01-base.gitlab-ci.yml"),
            str(FIXTURES / "m01-mutated.gitlab-ci.yml"),
            "--pipeline-name",
            "main",
        ]
    )

    assert status == 0
    assert capsys.readouterr().out == "main/security-scan\n"
