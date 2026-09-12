"""Format-independent dependency graph operations."""

from collections import deque
from collections.abc import Iterable
import networkx as nx
from capts.model import EdgeType, NodeType

IMPACT_EDGE_TYPES = {
    EdgeType.CONSUMES,
    EdgeType.INHERITS,
    EdgeType.EXECUTES,
}

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
