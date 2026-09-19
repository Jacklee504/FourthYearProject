from pathlib import Path

import yaml

from capts.adapters.gitlab import parse_gitlab_pipeline
from capts.diff import detect_changed_nodes
from capts.graph import select_affected_stages

FIXTURES = Path(__file__).parent / "fixtures"
M01_BASE = FIXTURES / "m01-base.gitlab-ci.yml"
M01_MUTATED = FIXTURES / "m01-mutated.gitlab-ci.yml"
M02_BASE = FIXTURES / "m02-base.gitlab-ci.yml"
M02_MUTATED = FIXTURES / "m02-mutated.gitlab-ci.yml"


def _load_pipeline(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as pipeline_file:
        return yaml.safe_load(pipeline_file)


def test_m01_rename_marks_the_removed_variable_as_changed() -> None:
    changed_nodes = detect_changed_nodes(
        _load_pipeline(M01_BASE), _load_pipeline(M01_MUTATED)
    )

    assert changed_nodes == {"SCAN_THRESHOLD"}


def test_m01_rename_selects_security_scan() -> None:
    graph = parse_gitlab_pipeline(M01_BASE, pipeline_name="main")
    changed_nodes = detect_changed_nodes(
        _load_pipeline(M01_BASE), _load_pipeline(M01_MUTATED)
    )

    assert select_affected_stages(graph, changed_nodes) == {"main/security-scan"}


def test_m02_rename_selects_all_consuming_stages() -> None:
    graph = parse_gitlab_pipeline(M02_BASE, pipeline_name="main")
    changed_nodes = detect_changed_nodes(
        _load_pipeline(M02_BASE), _load_pipeline(M02_MUTATED)
    )

    assert changed_nodes == {"FEATURE_FLAGS"}
    assert select_affected_stages(graph, changed_nodes) == {
        "main/unit-test",
        "main/smoke-test",
        "main/canary-test",
    }
