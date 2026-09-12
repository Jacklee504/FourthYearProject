"""Format-independent CAPTS graph types and adapter contract."""

from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

import networkx as nx

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


@runtime_checkable
class FormatAdapter(Protocol):
    """Maps one pipeline-definition format into the universal graph model."""

    def build_graph(self, path: str | Path, *, pipeline_name: str) -> nx.DiGraph:
        """Build a graph whose stages and templates use pipeline-qualified IDs."""
