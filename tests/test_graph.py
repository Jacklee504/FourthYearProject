import networkx as nx

from capts.graph import select_affected_stages
from capts.model import EdgeType, NodeType


def test_changed_variable_selects_all_consuming_stages() -> None:
    graph = nx.DiGraph()
    graph.add_node("variable:APP_MODE", node_type=NodeType.VARIABLE)
    graph.add_node("stage:build", node_type=NodeType.STAGE)
    graph.add_node("stage:test", node_type=NodeType.STAGE)
    graph.add_edge("stage:build", "variable:APP_MODE", edge_type=EdgeType.CONSUMES)
    graph.add_edge("stage:test", "variable:APP_MODE", edge_type=EdgeType.CONSUMES)

    assert select_affected_stages(graph, {"variable:APP_MODE"}) == {
        "stage:build",
        "stage:test",
    }


def test_depends_on_edge_does_not_propagate_impact() -> None:
    graph = nx.DiGraph()
    graph.add_node("stage:build", node_type=NodeType.STAGE)
    graph.add_node("stage:test", node_type=NodeType.STAGE)
    graph.add_edge("stage:test", "stage:build", edge_type=EdgeType.DEPENDS_ON)

    assert select_affected_stages(graph, {"stage:build"}) == {"stage:build"}


def test_unknown_changed_node_selects_nothing() -> None:
    graph = nx.DiGraph()
    graph.add_node("stage:build", node_type=NodeType.STAGE)

    assert select_affected_stages(graph, {"variable:MISSING"}) == set()
