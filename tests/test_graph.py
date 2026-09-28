import networkx as nx
import pytest

from capts.graph import (
    build_graph,
    enrich_changed_nodes,
    select_affected_stages,
    select_affected_with_triggers,
)
from capts.model import (
    ChangeEvent,
    ChangeType,
    EdgeInfo,
    EdgeType,
    NodeInfo,
    NodeType,
    PipelineModel,
)


def test_build_graph_preserves_model_nodes_and_edges() -> None:
    model = PipelineModel(
        nodes=[
            NodeInfo("main/build", NodeType.STAGE, pipeline="main"),
            NodeInfo("BUILD_CMD", NodeType.VARIABLE),
        ],
        edges=[EdgeInfo("main/build", "BUILD_CMD", EdgeType.CONSUMES)],
    )

    graph = build_graph(model)

    assert graph.nodes["main/build"]["node_type"] == NodeType.STAGE
    assert graph.nodes["main/build"]["pipeline"] == "main"
    assert graph.edges["main/build", "BUILD_CMD"]["edge_type"] == EdgeType.CONSUMES

def test_changed_variable_selects_all_consuming_stages() -> None:
    graph = nx.DiGraph()
    graph.add_node("APP_MODE", node_type=NodeType.VARIABLE)
    graph.add_node("main/build", node_type=NodeType.STAGE)
    graph.add_node("main/test", node_type=NodeType.STAGE)
    graph.add_edge("main/build", "APP_MODE", edge_type=EdgeType.CONSUMES)
    graph.add_edge("main/test", "APP_MODE", edge_type=EdgeType.CONSUMES)

    assert select_affected_stages(graph, {"APP_MODE"}) == {
        "main/build",
        "main/test",
    }

def test_depends_on_edge_does_not_propagate_impact() -> None:
    graph = nx.DiGraph()
    graph.add_node("main/build", node_type=NodeType.STAGE)
    graph.add_node("main/test", node_type=NodeType.STAGE)
    graph.add_edge("main/test", "main/build", edge_type=EdgeType.DEPENDS_ON)

    assert select_affected_stages(graph, {"main/build"}) == {"main/build"}

def test_unknown_changed_node_selects_nothing() -> None:
    graph = nx.DiGraph()
    graph.add_node("main/build", node_type=NodeType.STAGE)

    assert select_affected_stages(graph, {"MISSING"}) == set()


def test_multiple_changed_roots_are_combined_without_duplicate_stages() -> None:
    graph = nx.DiGraph()
    graph.add_node("BUILD_CMD", node_type=NodeType.VARIABLE)
    graph.add_node("scripts/build.py", node_type=NodeType.SCRIPT)
    graph.add_node("main/build", node_type=NodeType.STAGE)
    graph.add_edge("main/build", "BUILD_CMD", edge_type=EdgeType.CONSUMES)
    graph.add_edge("main/build", "scripts/build.py", edge_type=EdgeType.EXECUTES)

    assert select_affected_stages(graph, {"BUILD_CMD", "scripts/build.py"}) == {
        "main/build"
    }


def test_template_and_script_changes_propagate_to_stages() -> None:
    graph = nx.DiGraph()
    graph.add_node("main/.test-base", node_type=NodeType.TEMPLATE)
    graph.add_node("scripts/test_runner.py", node_type=NodeType.SCRIPT)
    graph.add_node("main/unit-test", node_type=NodeType.STAGE)
    graph.add_edge("main/unit-test", "main/.test-base", edge_type=EdgeType.INHERITS)
    graph.add_edge("main/unit-test", "scripts/test_runner.py", edge_type=EdgeType.EXECUTES)

    assert select_affected_stages(graph, {"main/.test-base"}) == {"main/unit-test"}
    assert select_affected_stages(graph, {"scripts/test_runner.py"}) == {"main/unit-test"}


def test_repeated_semantic_paths_select_a_stage_once() -> None:
    graph = nx.DiGraph()
    graph.add_node("FEATURE_FLAGS", node_type=NodeType.VARIABLE)
    graph.add_node("main/.test-base", node_type=NodeType.TEMPLATE)
    graph.add_node("main/unit-test", node_type=NodeType.STAGE)
    graph.add_edge("main/.test-base", "FEATURE_FLAGS", edge_type=EdgeType.CONSUMES)
    graph.add_edge("main/unit-test", "FEATURE_FLAGS", edge_type=EdgeType.CONSUMES)
    graph.add_edge("main/unit-test", "main/.test-base", edge_type=EdgeType.INHERITS)

    assert select_affected_stages(graph, {"FEATURE_FLAGS"}) == {"main/unit-test"}


def test_directly_changed_stage_is_selected_without_touching_unrelated_stages() -> None:
    graph = nx.DiGraph()
    graph.add_node("main/build", node_type=NodeType.STAGE)
    graph.add_node("main/lint", node_type=NodeType.STAGE)

    assert select_affected_stages(graph, {"main/build"}) == {"main/build"}


@pytest.mark.parametrize(
    ("removed", "dependent"),
    [
        ("main/security-scan", "main/gate"),
        ("deploy/smoke-test", "deploy/deploy-prod"),
    ],
)
def test_removed_stage_enriches_its_direct_dependent(
    removed: str, dependent: str
) -> None:
    graph = nx.DiGraph()
    for stage in (removed, dependent, "main/unrelated"):
        graph.add_node(stage, node_type=NodeType.STAGE)
    graph.add_edge(dependent, removed, edge_type=EdgeType.DEPENDS_ON)

    roots = enrich_changed_nodes(graph, [ChangeEvent(removed, ChangeType.REMOVED)])

    assert roots == {removed, dependent}
    assert select_affected_stages(graph, roots) == {removed, dependent}


def test_removed_stage_enriches_multiple_dependents() -> None:
    graph = nx.DiGraph()
    for stage in ("main/build", "main/test", "main/lint"):
        graph.add_node(stage, node_type=NodeType.STAGE)
    for dependent in ("main/test", "main/lint"):
        graph.add_edge(dependent, "main/build", edge_type=EdgeType.DEPENDS_ON)

    assert enrich_changed_nodes(graph, [ChangeEvent("main/build", ChangeType.REMOVED)]) == {
        "main/build", "main/test", "main/lint"
    }


def test_modified_stage_does_not_enrich_dependents() -> None:
    graph = nx.DiGraph()
    graph.add_node("main/build", node_type=NodeType.STAGE)
    graph.add_node("main/test", node_type=NodeType.STAGE)
    graph.add_edge("main/test", "main/build", edge_type=EdgeType.DEPENDS_ON)

    assert enrich_changed_nodes(graph, [ChangeEvent("main/build", ChangeType.MODIFIED)]) == {
        "main/build"
    }


def test_removed_non_stage_does_not_enrich_dependents() -> None:
    graph = nx.DiGraph()
    graph.add_node("BUILD_CMD", node_type=NodeType.VARIABLE)
    graph.add_node("main/build", node_type=NodeType.STAGE)
    graph.add_edge("main/build", "BUILD_CMD", edge_type=EdgeType.CONSUMES)

    assert enrich_changed_nodes(graph, [ChangeEvent("BUILD_CMD", ChangeType.REMOVED)]) == {
        "BUILD_CMD"
    }


def _trigger_model() -> PipelineModel:
    return PipelineModel(
        nodes=[
            NodeInfo("main/gate", NodeType.STAGE),
            NodeInfo("deploy/deploy-prod", NodeType.STAGE),
            NodeInfo("deploy/smoke-test", NodeType.STAGE),
            NodeInfo("canary/deploy-canary", NodeType.STAGE),
            NodeInfo("notify/send-notification", NodeType.STAGE),
            NodeInfo("BUILD_CMD", NodeType.VARIABLE),
            NodeInfo("main/.base", NodeType.TEMPLATE),
        ],
        edges=[
            EdgeInfo("main/gate", "BUILD_CMD", EdgeType.CONSUMES),
            EdgeInfo("main/gate", "main/.base", EdgeType.INHERITS),
        ],
        triggers={
            "main/gate": {"deploy/deploy-prod", "deploy/smoke-test", "canary/deploy-canary"},
            "deploy/deploy-prod": {"notify/send-notification"},
        },
    )


def test_direct_trigger_change_selects_child_pipelines() -> None:
    affected = select_affected_with_triggers(
        _trigger_model(),
        [ChangeEvent("main/gate", ChangeType.MODIFIED, {"trigger_changed": True})],
    )

    assert affected == {
        "main/gate", "deploy/deploy-prod", "deploy/smoke-test", "canary/deploy-canary"
    }


@pytest.mark.parametrize("changed", ["BUILD_CMD", "main/.base"])
def test_incidental_trigger_impact_does_not_expand(changed: str) -> None:
    assert select_affected_with_triggers(
        _trigger_model(), [ChangeEvent(changed, ChangeType.MODIFIED)]
    ) == {"main/gate"}


def test_child_change_does_not_select_parent_trigger() -> None:
    assert select_affected_with_triggers(
        _trigger_model(), [ChangeEvent("deploy/deploy-prod", ChangeType.MODIFIED)]
    ) == {"deploy/deploy-prod"}


def test_nested_trigger_expansion_requires_its_own_direct_change() -> None:
    affected = select_affected_with_triggers(
        _trigger_model(),
        [
            ChangeEvent("main/gate", ChangeType.MODIFIED, {"trigger_changed": True}),
            ChangeEvent("deploy/deploy-prod", ChangeType.MODIFIED, {"trigger_changed": True}),
        ],
    )

    assert affected == {
        "main/gate", "deploy/deploy-prod", "deploy/smoke-test",
        "canary/deploy-canary", "notify/send-notification",
    }


def test_trigger_expansion_deduplicates_selected_stages() -> None:
    affected = select_affected_with_triggers(
        _trigger_model(),
        [
            ChangeEvent("main/gate", ChangeType.MODIFIED, {"trigger_changed": True}),
            ChangeEvent("deploy/smoke-test", ChangeType.MODIFIED),
        ],
    )

    assert affected == {
        "main/gate", "deploy/deploy-prod", "deploy/smoke-test", "canary/deploy-canary"
    }


def test_removed_stage_enrichment_does_not_expand_incidental_trigger() -> None:
    model = _trigger_model()
    model.nodes.append(NodeInfo("main/build", NodeType.STAGE))
    model.edges.append(EdgeInfo("main/gate", "main/build", EdgeType.DEPENDS_ON))

    affected = select_affected_with_triggers(
        model, [ChangeEvent("main/build", ChangeType.REMOVED)]
    )

    assert affected == {"main/build", "main/gate"}
