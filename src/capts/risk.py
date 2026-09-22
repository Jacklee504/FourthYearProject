"""Deterministic risk scoring from the CAPTS graph model."""

from dataclasses import dataclass

import networkx as nx

from capts.model import ChangeEvent, NodeType

CHANGE_SEVERITY = {
    "removed": 1.0,
    "renamed": 0.9,
    "dependency_removed": 0.8,
    "modified": 0.7,
    "value_changed": 0.5,
    "dependency_added": 0.2,
}
WEIGHTS = {
    "critical_path": 0.30,
    "fan_out": 0.20,
    "directness": 0.20,
    "change_severity": 0.20,
    "cross_pipeline": 0.10,
}


@dataclass(frozen=True)
class RiskScore:
    """The deterministic risk of one affected stage."""

    stage: str
    overall: float
    critical_path: float
    fan_out: float
    directness: float
    change_severity: float
    cross_pipeline: float
    level: str


def compute_risk_score(
    graph: nx.DiGraph,
    changed_node: str,
    affected_stage: str,
    change: ChangeEvent,
) -> RiskScore:
    """Calculate the POC risk score for one affected stage."""
    scores = {
        "critical_path": _critical_path_score(graph, affected_stage),
        "fan_out": _fan_out_score(graph, affected_stage),
        "directness": _directness_score(graph, changed_node, affected_stage),
        "change_severity": _change_severity_score(change),
        "cross_pipeline": _cross_pipeline_score(graph, changed_node, affected_stage),
    }
    overall = sum(scores[name] * WEIGHTS[name] for name in WEIGHTS) * 100
    level = "CRITICAL" if overall >= 75 else "HIGH" if overall >= 50 else "MEDIUM" if overall >= 25 else "LOW"
    return RiskScore(stage=affected_stage, overall=overall, level=level, **scores)


def _critical_path_score(graph: nx.DiGraph, stage: str) -> float:
    stage_graph = _stage_graph(graph)
    terminal_stages = [node for node in stage_graph if stage_graph.in_degree(node) == 0]
    if stage in terminal_stages:
        return 1.0

    impact_graph = stage_graph.reverse(copy=False)
    distances = [
        nx.shortest_path_length(impact_graph, stage, terminal)
        for terminal in terminal_stages
        if nx.has_path(impact_graph, stage, terminal)
    ]
    if not distances:
        return 0.0

    undirected = stage_graph.to_undirected()
    diameter = nx.diameter(undirected) if nx.is_connected(undirected) else _max_path_length(stage_graph)
    return max(0.0, 1.0 - min(distances) / diameter)


def _fan_out_score(graph: nx.DiGraph, stage: str) -> float:
    impact_graph = graph.reverse(copy=False)
    downstream_stages = {
        node
        for node in nx.descendants(impact_graph, stage)
        if graph.nodes[node].get("node_type") == NodeType.STAGE
    }
    total_stages = sum(
        graph.nodes[node].get("node_type") == NodeType.STAGE for node in graph.nodes
    )
    return len(downstream_stages) / (total_stages - 1) if total_stages > 1 else 0.0


def _directness_score(
    graph: nx.DiGraph, changed_node: str, affected_stage: str
) -> float:
    if graph.has_edge(affected_stage, changed_node):
        return 1.0

    impact_graph = graph.reverse(copy=False)
    if not nx.has_path(impact_graph, changed_node, affected_stage):
        return 0.3
    distance = nx.shortest_path_length(impact_graph, changed_node, affected_stage)
    if distance == 1:
        return 1.0
    if distance == 2:
        return 0.7
    return max(0.3, 1.0 - distance * 0.2)


def _change_severity_score(change: ChangeEvent) -> float:
    return CHANGE_SEVERITY.get(change.change_type, 0.5)


def _cross_pipeline_score(
    graph: nx.DiGraph, changed_node: str, affected_stage: str
) -> float:
    changed_pipeline = graph.nodes[changed_node].get("pipeline", "")
    affected_pipeline = graph.nodes[affected_stage].get("pipeline", "")
    return 1.0 if changed_pipeline != affected_pipeline else 0.0


def _stage_graph(graph: nx.DiGraph) -> nx.DiGraph:
    stages = {
        node for node in graph if graph.nodes[node].get("node_type") == NodeType.STAGE
    }
    stage_graph = nx.DiGraph()
    stage_graph.add_nodes_from(stages)
    stage_graph.add_edges_from(
        (source, target) for source, target in graph.edges if source in stages and target in stages
    )
    return stage_graph


def _max_path_length(graph: nx.DiGraph) -> int:
    return max(
        (
            length
            for lengths in nx.all_pairs_shortest_path_length(graph)
            for length in lengths.values()
        ),
        default=0,
    )
