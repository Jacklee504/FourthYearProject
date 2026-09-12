from pathlib import Path

from capts.adapters.gitlab import parse_gitlab_pipeline
from capts.graph import select_affected_stages
from capts.model import EdgeType, NodeType


FIXTURE = Path(__file__).parent / "fixtures" / "simple.gitlab-ci.yml"


def test_gitlab_adapter_maps_variables_jobs_and_needs() -> None:
    graph = parse_gitlab_pipeline(FIXTURE)

    assert graph.nodes["variable:APP_MODE"]["node_type"] == NodeType.VARIABLE
    assert graph.nodes["stage:build"]["node_type"] == NodeType.STAGE
    assert graph.nodes["stage:test"]["node_type"] == NodeType.STAGE
    assert graph.edges["stage:build", "variable:APP_MODE"]["edge_type"] == EdgeType.CONSUMES
    assert graph.edges["stage:test", "stage:build"]["edge_type"] == EdgeType.DEPENDS_ON


def test_gitlab_variable_change_selects_its_consuming_jobs() -> None:
    graph = parse_gitlab_pipeline(FIXTURE)

    assert select_affected_stages(graph, {"variable:APP_MODE"}) == {
        "stage:build",
        "stage:test",
    }
