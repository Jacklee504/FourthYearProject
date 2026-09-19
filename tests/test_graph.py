import networkx as nx

from capts.graph import build_graph, select_affected_stages
from capts.model import EdgeInfo, EdgeType, NodeInfo, NodeType, PipelineModel


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
