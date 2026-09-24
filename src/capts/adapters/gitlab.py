"""Minimal GitLab CI adapter for the first CAPTS vertical slice."""
import ast
import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import yaml

from capts.graph import build_graph
from capts.model import (
    ChangeEvent,
    ChangeType,
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


@dataclass(frozen=True)
class VariableValidationError:
    """An undefined variable reference in one GitLab job."""

    stage_id: str
    variable_name: str


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

    def detect_changes(
        self,
        old_pipeline: Mapping[str, object] | str | Path,
        new_pipeline: Mapping[str, object] | str | Path,
        *,
        pipeline_name: str = "main",
        old_script_root: str | Path | None = None,
        new_script_root: str | Path | None = None,
    ) -> list[ChangeEvent]:
        """Report supported global-variable changes between two pipelines."""
        if not isinstance(old_pipeline, Mapping):
            old_pipeline = _read_pipeline(Path(old_pipeline))
        if not isinstance(new_pipeline, Mapping):
            new_pipeline = _read_pipeline(Path(new_pipeline))
        old_paths = _pipeline_paths(old_pipeline)
        new_paths = _pipeline_paths(new_pipeline)
        if old_paths is not None and new_paths is not None:
            old_pipelines = {
                name: _read_pipeline(Path(path)) for name, path in old_paths.items()
            }
            new_pipelines = {
                name: _read_pipeline(Path(path)) for name, path in new_paths.items()
            }
            changes = _variable_changes(
                _combined_variables(old_pipelines.values()),
                _combined_variables(new_pipelines.values()),
            )
            for name in old_pipelines.keys() | new_pipelines.keys():
                changes.extend(
                    event
                    for event in self.detect_changes(
                        old_pipelines.get(name, {}),
                        new_pipelines.get(name, {}),
                        pipeline_name=name,
                        old_script_root=old_script_root,
                        new_script_root=new_script_root,
                    )
                    if "/" in event.node_id
                )
            return _unique_changes(changes)

        old_variables = _global_variables(old_pipeline)
        new_variables = _global_variables(new_pipeline)
        changes = _variable_changes(old_variables, new_variables)

        old_templates = _templates(old_pipeline)
        new_templates = _templates(new_pipeline)
        for name, definition in old_templates.items():
            node_id = f"{pipeline_name}/{name}"
            if name not in new_templates:
                changes.append(ChangeEvent(node_id, ChangeType.REMOVED))
            elif new_templates[name] != definition:
                changes.append(ChangeEvent(node_id, ChangeType.MODIFIED))

        old_jobs = _jobs(old_pipeline)
        new_jobs = _jobs(new_pipeline)
        for name, definition in old_jobs.items():
            node_id = f"{pipeline_name}/{name}"
            if name not in new_jobs:
                changes.append(ChangeEvent(node_id, ChangeType.REMOVED))
            elif new_jobs[name] != definition:
                changes.append(ChangeEvent(node_id, ChangeType.MODIFIED))

        if old_script_root is not None and new_script_root is not None:
            old_scripts = _referenced_scripts(old_pipeline)
            new_scripts = _referenced_scripts(new_pipeline)
            for script_name in old_scripts & new_scripts:
                old_path = Path(old_script_root) / script_name
                new_path = Path(new_script_root) / script_name
                if old_path.is_file() and new_path.is_file() and _script_changed(
                    old_path, new_path
                ):
                    changes.append(ChangeEvent(script_name, ChangeType.MODIFIED))

        return changes

    def validate_variables(
        self,
        pipeline: Mapping[str, object],
        *,
        pipeline_name: str,
    ) -> list[VariableValidationError]:
        """Report variable references not defined globally or by their job."""
        global_variables = set(_global_variables(pipeline))
        errors = []

        for job_name, definition in _jobs(pipeline).items():
            local_variables = definition.get("variables", {})
            if not isinstance(local_variables, Mapping):
                raise TypeError("GitLab job variables must be a mapping.")
            for variable_name in sorted(_referenced_variables(definition)):
                if variable_name not in global_variables | set(local_variables):
                    errors.append(
                        VariableValidationError(
                            stage_id=f"{pipeline_name}/{job_name}",
                            variable_name=variable_name,
                        )
                    )

        return errors

    def resolve_selected_jobs(
        self,
        pipeline: Mapping[str, object],
        selected_stage_ids: Iterable[str],
        *,
        pipeline_name: str = "main",
    ) -> dict[str, Mapping[str, object]]:
        """Return the selected GitLab job definitions by qualified stage ID."""
        selected_ids = sorted(set(selected_stage_ids))
        selected_pipelines = {
            stage_id.partition("/")[0] for stage_id in selected_ids if "/" in stage_id
        }
        ecosystem = {
            name: definition
            for name in selected_pipelines
            if isinstance(definition := pipeline.get(name), Mapping)
        }
        pipelines = ecosystem if ecosystem.keys() == selected_pipelines else {pipeline_name: pipeline}

        jobs = {}
        for stage_id in selected_ids:
            name, separator, job_name = stage_id.partition("/")
            definition = _jobs(pipelines.get(name, {})).get(job_name) if separator else None
            if definition is None:
                raise ValueError(f"Unknown selected GitLab stage: {stage_id}")
            jobs[stage_id] = definition
        return jobs

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
        pending_templates = list(referenced_templates)
        while pending_templates:
            template_name = pending_templates.pop()
            template = templates[template_name]
            for parent_name in _extends(template.get("extends")):
                if parent_name in templates and parent_name not in referenced_templates:
                    referenced_templates.add(parent_name)
                    pending_templates.append(parent_name)
        for name in referenced_templates:
            _add_node(
                model,
                NodeInfo(f"{pipeline_name}/{name}", NodeType.TEMPLATE, pipeline_name)
            )
        scripts = {
            script_name
            for definition in [*jobs.values(), *(templates[name] for name in referenced_templates)]
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

        for template_name in referenced_templates:
            template = templates[template_name]
            template_id = f"{pipeline_name}/{template_name}"
            local_variables = template.get("variables", {})
            if not isinstance(local_variables, Mapping):
                raise TypeError("GitLab template variables must be a mapping.")

            for variable_name in _referenced_variables(template):
                if variable_name in global_variables and variable_name not in local_variables:
                    model.edges.append(
                        EdgeInfo(template_id, variable_name, EdgeType.CONSUMES)
                    )

            for parent_name in _extends(template.get("extends")):
                if parent_name in templates:
                    model.edges.append(
                        EdgeInfo(
                            template_id,
                            f"{pipeline_name}/{parent_name}",
                            EdgeType.INHERITS,
                        )
                    )

            for script_name in _scripts(template.get("script")):
                model.edges.append(EdgeInfo(template_id, script_name, EdgeType.EXECUTES))

def parse_gitlab_pipeline(path: str | Path, *, pipeline_name: str) -> nx.DiGraph:
    """Build a CAPTS graph from one GitLab pipeline file."""
    return build_graph(GitLabAdapter().parse(path, pipeline_name=pipeline_name))


def _referenced_variables(definition: object) -> set[str]:
    return {
        match.group(1) or match.group(2)
        for line in _strings(definition)
        for match in VARIABLE_PATTERN.finditer(line)
    }

def _referenced_scripts(pipeline: Mapping[str, object]) -> set[str]:
    return {
        script_name
        for definition in _jobs(pipeline).values()
        for script_name in _scripts(definition.get("script"))
    }

def _script_changed(old_path: Path, new_path: Path) -> bool:
    if old_path.suffix == new_path.suffix == ".py":
        return _script_semantic_hash(old_path) != _script_semantic_hash(new_path)
    return old_path.read_bytes() != new_path.read_bytes()

def _script_semantic_hash(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return hashlib.sha256(ast.dump(tree).encode()).hexdigest()

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

def _combined_variables(
    pipelines: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    variables: dict[str, object] = {}
    for pipeline in pipelines:
        variables.update(_global_variables(pipeline))
    return variables

def _variable_changes(
    old_variables: Mapping[str, object], new_variables: Mapping[str, object]
) -> list[ChangeEvent]:
    changes = []
    for name, value in old_variables.items():
        if name not in new_variables:
            changes.append(ChangeEvent(name, ChangeType.REMOVED))
        elif new_variables[name] != value:
            changes.append(ChangeEvent(name, ChangeType.MODIFIED))
    return changes

def _unique_changes(changes: Iterable[ChangeEvent]) -> list[ChangeEvent]:
    unique_changes = []
    seen = set()
    for change in changes:
        key = (change.node_id, change.change_type)
        if key not in seen:
            seen.add(key)
            unique_changes.append(change)
    return unique_changes

def _pipeline_paths(
    pipeline: Mapping[str, object],
) -> Mapping[str, str | Path] | None:
    paths = {
        name: path
        for name, path in pipeline.items()
        if isinstance(path, (str, Path))
    }
    if paths and len(paths) == len(pipeline):
        return paths
    return None

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
