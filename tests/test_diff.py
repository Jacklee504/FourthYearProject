from pathlib import Path

import yaml

from capts.adapters.gitlab import GitLabAdapter, parse_gitlab_pipeline
from capts.graph import select_affected_stages
from capts.model import ChangeType

FIXTURES = Path(__file__).parent / "fixtures"
M01_BASE = FIXTURES / "m01-base.gitlab-ci.yml"
M01_MUTATED = FIXTURES / "m01-mutated.gitlab-ci.yml"
M02_BASE = FIXTURES / "m02-base.gitlab-ci.yml"
M02_MUTATED = FIXTURES / "m02-mutated.gitlab-ci.yml"


def _load_pipeline(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as pipeline_file:
        return yaml.safe_load(pipeline_file)


def test_m01_rename_marks_the_removed_variable_as_changed() -> None:
    events = GitLabAdapter().detect_changes(
        _load_pipeline(M01_BASE), _load_pipeline(M01_MUTATED)
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("SCAN_THRESHOLD", ChangeType.REMOVED)
    ]


def test_changed_variable_value_is_reported_as_modified() -> None:
    events = GitLabAdapter().detect_changes(
        {"variables": {"SCAN_THRESHOLD": "high"}},
        {"variables": {"SCAN_THRESHOLD": "low"}},
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("SCAN_THRESHOLD", ChangeType.MODIFIED)
    ]


def test_m01_rename_selects_security_scan() -> None:
    graph = parse_gitlab_pipeline(M01_BASE, pipeline_name="main")
    events = GitLabAdapter().detect_changes(
        _load_pipeline(M01_BASE), _load_pipeline(M01_MUTATED)
    )
    changed_nodes = {event.node_id for event in events}

    assert select_affected_stages(graph, changed_nodes) == {"main/security-scan"}


def test_m02_rename_selects_all_consuming_stages() -> None:
    graph = parse_gitlab_pipeline(M02_BASE, pipeline_name="main")
    events = GitLabAdapter().detect_changes(
        _load_pipeline(M02_BASE), _load_pipeline(M02_MUTATED)
    )
    changed_nodes = {event.node_id for event in events}

    assert [(event.node_id, event.change_type) for event in events] == [
        ("FEATURE_FLAGS", ChangeType.REMOVED)
    ]
    assert select_affected_stages(graph, changed_nodes) == {
        "main/unit-test",
        "main/smoke-test",
        "main/canary-test",
    }
