from pathlib import Path

import pytest
import yaml

from capts.adapters.gitlab import GitLabAdapter
from capts.graph import build_graph, select_affected_stages

ECOSYSTEM = Path(__file__).parent / "fixtures" / "ecosystem"
BASE = {name: ECOSYSTEM / f"{name}.yml" for name in ("main", "deploy", "canary", "notify")}
CASES = [
    ("M-01", "SCAN_THRESHOLD", "SEC_THRESHOLD", {"main/security-scan"}),
    (
        "M-02", "FEATURE_FLAGS", "FF_ENABLED",
        {"main/unit-test", "deploy/smoke-test", "canary/canary-test"},
    ),
]


@pytest.mark.parametrize("case,old_name,new_name,expected", CASES)
def test_first_gitlab_mutations(
    tmp_path: Path, case: str, old_name: str, new_name: str, expected: set[str]
) -> None:
    adapter = GitLabAdapter()
    model = adapter.parse(BASE)
    with BASE["main"].open(encoding="utf-8") as source:
        mutated_main = yaml.safe_load(source)
    mutated_main["variables"][new_name] = mutated_main["variables"].pop(old_name)
    new_main = tmp_path / "main.yml"
    new_main.write_text(yaml.safe_dump(mutated_main), encoding="utf-8")
    mutated = {**BASE, "main": new_main}

    events = adapter.detect_changes(BASE, mutated)
    selected = select_affected_stages(build_graph(model), {event.node_id for event in events})

    assert selected == expected, f"{case}: expected {expected}, selected {selected}"
