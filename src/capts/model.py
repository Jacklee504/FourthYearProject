"""Format-independent CAPTS graph types and model data."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable


class NodeType(StrEnum):
    """Kinds of pipeline resource represented in the dependency graph."""
    STAGE = "stage"
    VARIABLE = "variable"
    TEMPLATE = "template"
    SCRIPT = "script"

class EdgeType(StrEnum):
    """Relationships stored from a dependent to its dependency."""
    CONSUMES = "consumes"
    INHERITS = "inherits"
    DEPENDS_ON = "depends_on"
    EXECUTES = "executes"


class ChangeType(StrEnum):
    """Kinds of change that an adapter can report."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    RENAMED = "renamed"


@dataclass
class NodeInfo:
    """One format-independent pipeline node."""

    id: str
    node_type: NodeType
    pipeline: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class EdgeInfo:
    """One dependent-to-dependency relationship."""

    source: str
    target: str
    edge_type: EdgeType


@dataclass
class PipelineModel:
    """The format-independent representation returned by an adapter."""

    nodes: list[NodeInfo] = field(default_factory=list)
    edges: list[EdgeInfo] = field(default_factory=list)
    triggers: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class ChangeEvent:
    """A typed change between two pipeline-definition versions."""

    node_id: str
    change_type: ChangeType
    details: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class FormatAdapter(Protocol):
    """Maps one pipeline-definition format into the universal graph model."""

    def parse(
        self,
        path: str | Path | Mapping[str, str | Path],
        *,
        pipeline_name: str | None = None,
    ) -> PipelineModel:
        """Parse one or more pipeline files into the universal model."""

    def detect_changes(
        self,
        old_pipeline: Mapping[str, object],
        new_pipeline: Mapping[str, object],
    ) -> list[ChangeEvent]:
        """Compare two pipeline definitions and report typed changes."""
