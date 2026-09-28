"""Format-independent dependency graph operations."""

from collections import deque
from collections.abc import Iterable

import networkx as nx

from capts.model import ChangeEvent, ChangeType, EdgeType, NodeType, PipelineModel

IMPACT_EDGE_TYPES = {
    EdgeType.CONSUMES,
    EdgeType.INHERITS,
    EdgeType.EXECUTES,
}


def build_graph(model: PipelineModel) -> nx.DiGraph:
    """Convert the universal model into CAPTS's traversal graph."""
    graph = nx.DiGraph()

    for node in model.nodes:
        graph.add_node(
            node.id,
            node_type=node.node_type,
            pipeline=node.pipeline,
            **node.metadata,
        )

    for edge in model.edges:
        graph.add_edge(edge.source, edge.target, edge_type=edge.edge_type)

    return graph


def enrich_changed_nodes(
    graph: nx.DiGraph, changes: Iterable[ChangeEvent]
) -> set[str]:
    """Add direct dependents of removed stages to the changed roots."""
    events = list(changes)
    changed = {event.node_id for event in events}
    for event in events:
        if (
            event.change_type != ChangeType.REMOVED
            or event.node_id not in graph
            or graph.nodes[event.node_id].get("node_type") != NodeType.STAGE
        ):
            continue
        for dependent in graph.predecessors(event.node_id):
            if (
                graph.nodes[dependent].get("node_type") == NodeType.STAGE
                and graph.edges[dependent, event.node_id].get("edge_type")
                == EdgeType.DEPENDS_ON
            ):
                changed.add(dependent)
    return changed

def select_affected_stages(
    graph: nx.DiGraph, changed_nodes: Iterable[str]
) -> set[str]:
    """Return stages semantically affected by the supplied changed nodes.

    Edges are stored as dependent -> dependency. Reversing the graph therefore
    gives the direction needed to traverse from a changed resource to its
    consumers. ``depends_on`` is intentionally excluded because it represents
    execution ordering rather than semantic impact.
    """
    impact_graph = graph.reverse(copy=False)
    affected: set[str] = set()

    for changed_node in changed_nodes:
        if changed_node not in graph:
            continue

        queue = deque([changed_node])
        visited = {changed_node}
        while queue:
            current = queue.popleft()
            for consumer in impact_graph.successors(current):
                edge_type = graph.edges[consumer, current]["edge_type"]
                if edge_type not in IMPACT_EDGE_TYPES or consumer in visited:
                    continue
                visited.add(consumer)
                queue.append(consumer)

        affected.update(visited)

    return {
        node
        for node in affected
        if graph.nodes[node].get("node_type") == NodeType.STAGE
    }


def select_affected_with_triggers(
    model: PipelineModel, changes: Iterable[ChangeEvent]
) -> set[str]:
    """Select semantic impacts and children of directly changed triggers."""
    events = list(changes)
    graph = build_graph(model)
    affected = select_affected_stages(graph, enrich_changed_nodes(graph, events))
    direct_triggers = {
        event.node_id for event in events if event.details.get("trigger_changed") is True
    }
    expanded: set[str] = set()
    while pending := (direct_triggers & affected) - expanded:
        trigger_job = min(pending)
        expanded.add(trigger_job)
        affected.update(model.triggers.get(trigger_job, set()))
    return affected
