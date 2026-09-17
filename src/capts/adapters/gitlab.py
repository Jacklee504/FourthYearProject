"""Minimal GitLab CI adapter for the first CAPTS vertical slice."""
from collections.abc import Iterable, Mapping
from pathlib import Path
import re
import networkx as nx
import yaml
from capts.graph import build_graph
from capts.model import EdgeInfo, EdgeType, FormatAdapter, NodeInfo, NodeType, PipelineModel

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
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)}|([A-Za-z_][A-Za-z0-9_]*))"
)

class GitLabAdapter(FormatAdapter):
    """Map the first supported GitLab CI features into the CAPTS model."""

    def parse(self, path: str | Path, *, pipeline_name: str) -> PipelineModel:
        """Map global variables, jobs, and ``needs`` into a pipeline model.

        Stages use ``pipeline/job`` IDs. Variables remain global IDs because
        every pipeline in the synthetic ecosystem shares the same variables.
        """
        with Path(path).open(encoding="utf-8") as pipeline_file:
            pipeline = yaml.safe_load(pipeline_file) or {}

        if not isinstance(pipeline, dict):
            raise ValueError("A GitLab pipeline must be a YAML mapping.")

        model = PipelineModel()
        global_variables = pipeline.get("variables", {})
        if not isinstance(global_variables, dict):
            raise ValueError("GitLab global variables must be a mapping.")

        for name in global_variables:
            model.nodes.append(NodeInfo(name, NodeType.VARIABLE))

        jobs = {
            name: definition
            for name, definition in pipeline.items()
            if name not in GITLAB_GLOBAL_KEYS
            and not name.startswith(".")
            and isinstance(definition, dict)
        }
        for name in jobs:
            model.nodes.append(
                NodeInfo(f"{pipeline_name}/{name}", NodeType.STAGE, pipeline_name)
            )

        for job_name, definition in jobs.items():
            stage_id = f"{pipeline_name}/{job_name}"
            local_variables = definition.get("variables", {})
            if not isinstance(local_variables, Mapping):
                raise ValueError("GitLab job variables must be a mapping.")

            for variable_name in _referenced_variables(definition):
                if variable_name in global_variables and variable_name not in local_variables:
                    model.edges.append(
                        EdgeInfo(stage_id, variable_name, EdgeType.CONSUMES)
                    )

            for dependency in _needs(definition.get("needs")):
                dependency_id = f"{pipeline_name}/{dependency}"
                if dependency in jobs:
                    model.edges.append(
                        EdgeInfo(stage_id, dependency_id, EdgeType.DEPENDS_ON)
                    )

        return model

def parse_gitlab_pipeline(path: str | Path, *, pipeline_name: str) -> nx.DiGraph:
    """Build a CAPTS graph from one GitLab pipeline file."""
    return build_graph(GitLabAdapter().parse(path, pipeline_name=pipeline_name))


def _referenced_variables(definition: object) -> set[str]:
    return {
        match.group(1) or match.group(2)
        for line in _strings(definition)
        for match in VARIABLE_PATTERN.finditer(line)
    }

def _strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested_value in value.values():
            yield from _strings(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _strings(nested_value)

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
