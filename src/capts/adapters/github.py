"""Parse supported GitHub Actions jobs into the universal model."""
import re
from collections.abc import Mapping
from pathlib import Path

import yaml

from capts.model import EdgeInfo, EdgeType, NodeInfo, NodeType, PipelineModel

VARIABLE = re.compile(r"\$\{\{\s*(env|vars|secrets)\.([A-Za-z_][A-Za-z0-9_]*)\s*}}")
SCRIPT = re.compile(r"\bscripts/[A-Za-z0-9_./-]+")
WORKFLOW = "./.github/workflows/"


class GitHubActionsAdapter:
    """Map the first supported GitHub Actions features into a PipelineModel."""

    def parse(
        self,
        path: str | Path | Mapping[str, str | Path],
        *,
        pipeline_name: str | None = None,
    ) -> PipelineModel:
        if isinstance(path, Mapping):
            if pipeline_name is not None:
                raise ValueError("Provide a pipeline name only for one workflow file.")
            paths = path
        elif pipeline_name is not None:
            paths = {pipeline_name: path}
        else:
            raise ValueError("A pipeline name is required for one workflow file.")

        workflows = {}
        for name, file_path in paths.items():
            with Path(file_path).open(encoding="utf-8") as source:
                workflow = yaml.safe_load(source) or {}
            if not isinstance(workflow, Mapping):
                raise TypeError("A GitHub Actions workflow must be a YAML mapping.")
            workflows[name] = workflow

        globals_ = {
            name
            for workflow in workflows.values()
            for name in _mapping(workflow.get("env"))
        }
        model = PipelineModel(nodes=[NodeInfo(name, NodeType.VARIABLE) for name in sorted(globals_)])
        seen = globals_.copy()
        for workflow_name, workflow in workflows.items():
            jobs = _mapping(workflow.get("jobs"))
            for job_name, value in jobs.items():
                if not isinstance(value, Mapping):
                    continue
                stage_id = f"{workflow_name}/{job_name}"
                model.nodes.append(NodeInfo(stage_id, NodeType.STAGE, workflow_name))
                local = _mapping(value.get("env"))
                for text in _strings(value):
                    for scope, name in VARIABLE.findall(text):
                        node_id = name if scope == "env" else f"{scope}.{name}"
                        if scope == "env" and (name not in globals_ or name in local):
                            continue
                        if node_id not in seen:
                            model.nodes.append(NodeInfo(node_id, NodeType.VARIABLE))
                            seen.add(node_id)
                        edge = EdgeInfo(stage_id, node_id, EdgeType.CONSUMES)
                        if edge not in model.edges:
                            model.edges.append(edge)

                needs = value.get("needs", [])
                if isinstance(needs, str):
                    needs = [needs]
                if isinstance(needs, list):
                    for dependency in needs:
                        if isinstance(dependency, str) and dependency in jobs:
                            model.edges.append(EdgeInfo(stage_id, f"{workflow_name}/{dependency}", EdgeType.DEPENDS_ON))

                uses = value.get("uses")
                if isinstance(uses, str) and uses.startswith(WORKFLOW):
                    template_id = uses.removeprefix("./")
                    if template_id not in seen:
                        model.nodes.append(NodeInfo(template_id, NodeType.TEMPLATE))
                        seen.add(template_id)
                    model.edges.append(EdgeInfo(stage_id, template_id, EdgeType.INHERITS))

                commands = [step.get("run") for step in value.get("steps", []) if isinstance(step, Mapping)] if isinstance(value.get("steps"), list) else []
                commands.append(_mapping(value.get("with")).get("script"))
                for command in commands:
                    if isinstance(command, str):
                        for script_id in SCRIPT.findall(command):
                            if script_id not in seen:
                                model.nodes.append(NodeInfo(script_id, NodeType.SCRIPT))
                                seen.add(script_id)
                            edge = EdgeInfo(stage_id, script_id, EdgeType.EXECUTES)
                            if edge not in model.edges:
                                model.edges.append(edge)
        return model


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []
