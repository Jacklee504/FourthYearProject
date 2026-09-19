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


def _write_script(root: Path, script_name: str, content: str) -> None:
    script = root / script_name
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(content, encoding="utf-8")


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


def test_semantically_unchanged_script_has_no_change_event(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    pipeline = {"security-scan": {"script": "python scripts/scan.py"}}
    _write_script(old_root, "scripts/scan.py", "def scan():\n    return 'high'\n")
    _write_script(
        new_root,
        "scripts/scan.py",
        "# Scan the current project.\n\ndef scan():\n    return 'high'\n",
    )

    events = GitLabAdapter().detect_changes(
        pipeline,
        pipeline,
        old_script_root=old_root,
        new_script_root=new_root,
    )

    assert events == []


def test_changed_script_selects_its_executing_stage(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    pipeline = {"security-scan": {"script": "python scripts/scan.py"}}
    _write_script(old_root, "scripts/scan.py", "def scan():\n    return 'high'\n")
    _write_script(new_root, "scripts/scan.py", "def scan():\n    return 'low'\n")
    pipeline_path = old_root / "pipeline.yml"
    pipeline_path.write_text(
        "security-scan:\n  script: python scripts/scan.py\n",
        encoding="utf-8",
    )

    events = GitLabAdapter().detect_changes(
        pipeline,
        pipeline,
        old_script_root=old_root,
        new_script_root=new_root,
    )
    changed_nodes = {event.node_id for event in events}

    assert [(event.node_id, event.change_type) for event in events] == [
        ("scripts/scan.py", ChangeType.MODIFIED)
    ]
    graph = parse_gitlab_pipeline(pipeline_path, pipeline_name="main")
    assert select_affected_stages(graph, changed_nodes) == {"main/security-scan"}


def test_changed_shared_script_selects_all_executing_stages(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    pipeline = {
        "unit-test": {"script": "python scripts/test_runner.py"},
        "smoke-test": {"script": "python scripts/test_runner.py"},
    }
    _write_script(old_root, "scripts/test_runner.py", "def run():\n    return True\n")
    _write_script(new_root, "scripts/test_runner.py", "def run():\n    return False\n")
    pipeline_path = old_root / "pipeline.yml"
    pipeline_path.write_text(
        "unit-test:\n  script: python scripts/test_runner.py\n"
        "smoke-test:\n  script: python scripts/test_runner.py\n",
        encoding="utf-8",
    )

    events = GitLabAdapter().detect_changes(
        pipeline,
        pipeline,
        old_script_root=old_root,
        new_script_root=new_root,
    )
    changed_nodes = {event.node_id for event in events}
    graph = parse_gitlab_pipeline(pipeline_path, pipeline_name="main")

    assert changed_nodes == {"scripts/test_runner.py"}
    assert select_affected_stages(graph, changed_nodes) == {
        "main/unit-test",
        "main/smoke-test",
    }
