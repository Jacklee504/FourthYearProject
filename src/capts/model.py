"""Format-independent graph labels used by CAPTS."""

from enum import StrEnum


class NodeType(StrEnum):
    """Kinds of pipeline resource represented in the dependency graph."""

    STAGE = "stage"
    VARIABLE = "variable"


class EdgeType(StrEnum):
    """Relationships stored from a dependent to its dependency."""

    CONSUMES = "consumes"
    DEPENDS_ON = "depends_on"
