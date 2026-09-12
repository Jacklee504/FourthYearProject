"""Minimal GitLab CI adapter for the first CAPTS vertical slice."""

from collections.abc import Iterable
from pathlib import Path
import re

import networkx as nx
import yaml

from capts.model import EdgeType, NodeType


GITLAB_GLOBAL_KEYS = {
    "after_script",
    "before_script",
    "cache",
    "default",
    "image",
    "include",
    "services",
    "stages",
    "variables",
    "workflow",
}
VARIABLE_PATTERN = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"
)


def parse_gitlab_pipeline(path: str | Path) -> nx.DiGraph:
    """Map global variables, job scripts, and ``needs`` into a graph.

    This deliberately supports only the first milestone. Templates, includes,
    triggers, local variable overrides, and other GitLab features follow in
    later increments.
    """
    with Path(path).open(encoding="utf-8") as pipeline_file:
        pipeline = yaml.safe_load(pipeline_file) or {}

    if not isinstance(pipeline, dict):
        raise ValueError("A GitLab pipeline must be a YAML mapping.")

    graph = nx.DiGraph()
    global_variables = pipeline.get("variables", {})
    if not isinstance(global_variables, dict):
        raise ValueError("GitLab global variables must be a mapping.")

    for name in global_variables:
        graph.add_node(f"variable:{name}", node_type=NodeType.VARIABLE)

    jobs = {
        name: definition
        for name, definition in pipeline.items()
        if name not in GITLAB_GLOBAL_KEYS
        and not name.startswith(".")
        and isinstance(definition, dict)
    }
    for name in jobs:
        graph.add_node(f"stage:{name}", node_type=NodeType.STAGE)

    for job_name, definition in jobs.items():
        stage_id = f"stage:{job_name}"
        for variable_name in _referenced_variables(definition.get("script")):
            variable_id = f"variable:{variable_name}"
            if variable_id in graph:
                graph.add_edge(stage_id, variable_id, edge_type=EdgeType.CONSUMES)

        for dependency in _needs(definition.get("needs")):
            dependency_id = f"stage:{dependency}"
            if dependency_id in graph:
                graph.add_edge(
                    stage_id,
                    dependency_id,
                    edge_type=EdgeType.DEPENDS_ON,
                )

    return graph


def _referenced_variables(script: object) -> set[str]:
    if isinstance(script, str):
        strings: Iterable[str] = (script,)
    elif isinstance(script, list) and all(isinstance(line, str) for line in script):
        strings = script
    else:
        strings = ()

    return {
        match.group(1) or match.group(2)
        for line in strings
        for match in VARIABLE_PATTERN.finditer(line)
    }


def _needs(needs: object) -> set[str]:
    if not isinstance(needs, list):
        return set()

    dependency_names = set()
    for dependency in needs:
        if isinstance(dependency, str):
            dependency_names.add(dependency)
        elif isinstance(dependency, dict) and isinstance(dependency.get("job"), str):
            dependency_names.add(dependency["job"])
    return dependency_names
