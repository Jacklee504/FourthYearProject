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


def _write_pipeline(path: Path, pipeline: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(pipeline), encoding="utf-8")


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


def test_unchanged_template_has_no_change_event() -> None:
    pipeline = {".test-base": {"image": "python:3.12"}}

    events = GitLabAdapter().detect_changes(pipeline, pipeline)

    assert events == []


def test_modified_template_is_reported() -> None:
    events = GitLabAdapter().detect_changes(
        {".test-base": {"image": "python:3.12"}},
        {".test-base": {"image": "python:3.13"}},
        pipeline_name="main",
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("main/.test-base", ChangeType.MODIFIED)
    ]


def test_removed_template_is_reported() -> None:
    events = GitLabAdapter().detect_changes(
        {".test-base": {"image": "python:3.12"}},
        {},
        pipeline_name="main",
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("main/.test-base", ChangeType.REMOVED)
    ]


def test_changed_template_selects_inheriting_job(tmp_path: Path) -> None:
    old_pipeline = {
        ".test-base": {"image": "python:3.12"},
        "unit-test": {"extends": ".test-base"},
    }
    new_pipeline = {
        ".test-base": {"image": "python:3.13"},
        "unit-test": {"extends": ".test-base"},
    }
    pipeline_path = tmp_path / "pipeline.yml"
    pipeline_path.write_text(
        ".test-base:\n  image: python:3.12\nunit-test:\n  extends: .test-base\n",
        encoding="utf-8",
    )

    events = GitLabAdapter().detect_changes(
        old_pipeline, new_pipeline, pipeline_name="main"
    )
    graph = parse_gitlab_pipeline(pipeline_path, pipeline_name="main")

    assert select_affected_stages(
        graph, {event.node_id for event in events}
    ) == {"main/unit-test"}


def test_unchanged_job_has_no_change_event() -> None:
    pipeline = {"security-scan": {"script": "echo scan"}}

    events = GitLabAdapter().detect_changes(pipeline, pipeline)

    assert events == []


def test_changed_job_is_reported() -> None:
    events = GitLabAdapter().detect_changes(
        {"security-scan": {"script": "echo scan"}},
        {"security-scan": {"script": "echo scan", "retry": 2}},
        pipeline_name="main",
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("main/security-scan", ChangeType.MODIFIED)
    ]


def test_removed_job_is_reported() -> None:
    events = GitLabAdapter().detect_changes(
        {"security-scan": {"script": "echo scan"}},
        {},
        pipeline_name="main",
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("main/security-scan", ChangeType.REMOVED)
    ]


def test_changed_job_selects_only_that_job_not_its_dependents(tmp_path: Path) -> None:
    old_pipeline = {
        "build": {"script": "echo build"},
        "unit-test": {"needs": ["build"], "script": "echo test"},
    }
    new_pipeline = {
        "build": {"script": "echo updated build"},
        "unit-test": {"needs": ["build"], "script": "echo test"},
    }
    pipeline_path = tmp_path / "pipeline.yml"
    pipeline_path.write_text(
        "build:\n  script: echo build\nunit-test:\n  needs: [build]\n  script: echo test\n",
        encoding="utf-8",
    )

    events = GitLabAdapter().detect_changes(
        old_pipeline, new_pipeline, pipeline_name="main"
    )
    graph = parse_gitlab_pipeline(pipeline_path, pipeline_name="main")

    assert select_affected_stages(
        graph, {event.node_id for event in events}
    ) == {"main/build"}


def test_multi_pipeline_changes_keep_same_named_jobs_distinct(tmp_path: Path) -> None:
    old_main = tmp_path / "old-main.yml"
    new_main = tmp_path / "new-main.yml"
    old_deploy = tmp_path / "old-deploy.yml"
    new_deploy = tmp_path / "new-deploy.yml"
    _write_pipeline(old_main, {"build": {"script": "echo build"}})
    _write_pipeline(new_main, {"build": {"script": "echo updated build"}})
    _write_pipeline(old_deploy, {"build": {"script": "echo deploy"}})
    _write_pipeline(new_deploy, {"build": {"script": "echo deploy"}})

    events = GitLabAdapter().detect_changes(
        {"main": old_main, "deploy": old_deploy},
        {"main": new_main, "deploy": new_deploy},
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("main/build", ChangeType.MODIFIED)
    ]


def test_multi_pipeline_template_changes_remain_qualified(tmp_path: Path) -> None:
    old_main = tmp_path / "old-main.yml"
    new_main = tmp_path / "new-main.yml"
    old_deploy = tmp_path / "old-deploy.yml"
    new_deploy = tmp_path / "new-deploy.yml"
    _write_pipeline(old_main, {".base": {"image": "python:3.12"}})
    _write_pipeline(new_main, {".base": {"image": "python:3.12"}})
    _write_pipeline(old_deploy, {".base": {"image": "python:3.12"}})
    _write_pipeline(new_deploy, {".base": {"image": "python:3.13"}})

    events = GitLabAdapter().detect_changes(
        {"main": old_main, "deploy": old_deploy},
        {"main": new_main, "deploy": new_deploy},
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("deploy/.base", ChangeType.MODIFIED)
    ]


def test_multi_pipeline_shared_variable_change_is_not_duplicated(tmp_path: Path) -> None:
    old_main = tmp_path / "old-main.yml"
    new_main = tmp_path / "new-main.yml"
    old_deploy = tmp_path / "old-deploy.yml"
    new_deploy = tmp_path / "new-deploy.yml"
    for path in (old_main, old_deploy):
        _write_pipeline(path, {"variables": {"SHARED_VALUE": "old"}})
    for path in (new_main, new_deploy):
        _write_pipeline(path, {"variables": {"SHARED_VALUE": "new"}})

    events = GitLabAdapter().detect_changes(
        {"main": old_main, "deploy": old_deploy},
        {"main": new_main, "deploy": new_deploy},
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("SHARED_VALUE", ChangeType.MODIFIED)
    ]


def test_multi_pipeline_child_change_is_not_attributed_to_main(tmp_path: Path) -> None:
    old_main = tmp_path / "old-main.yml"
    new_main = tmp_path / "new-main.yml"
    old_deploy = tmp_path / "old-deploy.yml"
    new_deploy = tmp_path / "new-deploy.yml"
    _write_pipeline(old_main, {"gate": {"script": "echo gate"}})
    _write_pipeline(new_main, {"gate": {"script": "echo gate"}})
    _write_pipeline(old_deploy, {"deploy-prod": {"script": "echo deploy"}})
    _write_pipeline(new_deploy, {"deploy-prod": {"script": "echo updated deploy"}})

    events = GitLabAdapter().detect_changes(
        {"main": old_main, "deploy": old_deploy},
        {"main": new_main, "deploy": new_deploy},
    )

    assert [(event.node_id, event.change_type) for event in events] == [
        ("deploy/deploy-prod", ChangeType.MODIFIED)
    ]


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
