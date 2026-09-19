"""Minimal GitLab CI adapter for the first CAPTS vertical slice."""
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import networkx as nx
import yaml

from capts.graph import build_graph
from capts.model import (
    EdgeInfo,
    EdgeType,
    FormatAdapter,
    NodeInfo,
    NodeType,
    PipelineModel,
)

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

    def parse(
        self,
        path: str | Path | Mapping[str, str | Path],
        *,
        pipeline_name: str | None = None,
    ) -> PipelineModel:
        """Map one or more GitLab pipeline files into a pipeline model.

        Stages use ``pipeline/job`` IDs. Variables remain global IDs because
        every pipeline in the synthetic ecosystem shares the same variables.
        """
        if isinstance(path, Mapping):
            if pipeline_name is not None:
                raise ValueError("Provide a pipeline name only for one pipeline file.")
            pipeline_paths = {name: Path(file_path) for name, file_path in path.items()}
        elif pipeline_name is not None:
            pipeline_paths = {pipeline_name: Path(path)}
        else:
            raise ValueError("A pipeline name is required for one pipeline file.")

        pipelines = {
            name: _read_pipeline(file_path) for name, file_path in pipeline_paths.items()
        }
        global_variables = {
            variable_name
            for pipeline in pipelines.values()
            for variable_name in _global_variables(pipeline)
        }
        model = PipelineModel()
        for name in global_variables:
            _add_node(model, NodeInfo(name, NodeType.VARIABLE))

        pipeline_jobs = {}
        for name, pipeline in pipelines.items():
            jobs = _jobs(pipeline)
            pipeline_jobs[name] = jobs
            self._add_pipeline(model, name, pipeline, jobs, global_variables)

        pipeline_names_by_path = {
            file_path.resolve(): name for name, file_path in pipeline_paths.items()
        }
        for name, jobs in pipeline_jobs.items():
            for job_name, definition in jobs.items():
                child_names = {
                    pipeline_names_by_path[child_path]
                    for child_path in _trigger_paths(definition.get("trigger"), pipeline_paths[name])
                    if child_path in pipeline_names_by_path
                }
                if child_names:
                    model.triggers[f"{name}/{job_name}"] = {
                        node.id
                        for node in model.nodes
                        if node.node_type == NodeType.STAGE and node.pipeline in child_names
                    }

        return model

    def _add_pipeline(
        self,
        model: PipelineModel,
        pipeline_name: str,
        pipeline: Mapping[str, object],
        jobs: Mapping[str, Mapping[str, object]],
        global_variables: set[str],
    ) -> None:
        """Add one parsed pipeline to a combined model."""
        templates = _templates(pipeline)

        for name in jobs:
            _add_node(
                model,
                NodeInfo(f"{pipeline_name}/{name}", NodeType.STAGE, pipeline_name)
            )
        referenced_templates = {
            template_name
            for definition in jobs.values()
            for template_name in _extends(definition.get("extends"))
            if template_name in templates
        }
        for name in referenced_templates:
            _add_node(
                model,
                NodeInfo(f"{pipeline_name}/{name}", NodeType.TEMPLATE, pipeline_name)
            )
        scripts = {
            script_name
            for definition in jobs.values()
            for script_name in _scripts(definition.get("script"))
        }
        for name in scripts:
            _add_node(model, NodeInfo(name, NodeType.SCRIPT))

        for job_name, definition in jobs.items():
            stage_id = f"{pipeline_name}/{job_name}"
            local_variables = definition.get("variables", {})
            if not isinstance(local_variables, Mapping):
                raise TypeError("GitLab job variables must be a mapping.")

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

            for template_name in _extends(definition.get("extends")):
                if template_name in templates:
                    model.edges.append(
                        EdgeInfo(
                            stage_id,
                            f"{pipeline_name}/{template_name}",
                            EdgeType.INHERITS,
                        )
                    )

            for script_name in _scripts(definition.get("script")):
                model.edges.append(EdgeInfo(stage_id, script_name, EdgeType.EXECUTES))

def parse_gitlab_pipeline(path: str | Path, *, pipeline_name: str) -> nx.DiGraph:
    """Build a CAPTS graph from one GitLab pipeline file."""
    return build_graph(GitLabAdapter().parse(path, pipeline_name=pipeline_name))


def _referenced_variables(definition: object) -> set[str]:
    return {
        match.group(1) or match.group(2)
        for line in _strings(definition)
        for match in VARIABLE_PATTERN.finditer(line)
    }

def _read_pipeline(path: Path) -> Mapping[str, object]:
    with path.open(encoding="utf-8") as pipeline_file:
        pipeline = yaml.safe_load(pipeline_file) or {}
    if not isinstance(pipeline, dict):
        raise TypeError("A GitLab pipeline must be a YAML mapping.")
    return pipeline

def _global_variables(pipeline: Mapping[str, object]) -> Mapping[str, object]:
    variables = pipeline.get("variables", {})
    if not isinstance(variables, Mapping):
        raise TypeError("GitLab global variables must be a mapping.")
    return variables

def _jobs(pipeline: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    return {
        name: definition
        for name, definition in pipeline.items()
        if name not in GITLAB_GLOBAL_KEYS
        and not name.startswith(".")
        and isinstance(definition, Mapping)
    }

def _templates(pipeline: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    return {
        name: definition
        for name, definition in pipeline.items()
        if name.startswith(".") and isinstance(definition, Mapping)
    }

def _add_node(model: PipelineModel, node: NodeInfo) -> None:
    if node.id not in {existing.id for existing in model.nodes}:
        model.nodes.append(node)

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

def _extends(extends: object) -> list[str]:
    if isinstance(extends, str):
        return [extends]
    if isinstance(extends, list):
        return [template for template in extends if isinstance(template, str)]
    return []

def _scripts(script: object) -> set[str]:
    if isinstance(script, str):
        script = [script]
    if not isinstance(script, list):
        return set()
    return {
        part.split("--", maxsplit=1)[0]
        for line in script
        if isinstance(line, str)
        for part in line.split()
        if part.startswith("scripts/")
    }

def _trigger_paths(trigger: object, parent_path: Path) -> set[Path]:
    if not isinstance(trigger, Mapping):
        return set()
    includes = trigger.get("include", [])
    if isinstance(includes, (str, Mapping)):
        includes = [includes]
    if not isinstance(includes, list):
        return set()
    return {
        (parent_path.parent / include["local"]).resolve()
        for include in includes
        if isinstance(include, Mapping) and isinstance(include.get("local"), str)
    }
