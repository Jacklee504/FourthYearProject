"""Map supported differences between pipeline definitions to graph nodes."""
from collections.abc import Mapping

def detect_changed_nodes(
    old_pipeline: Mapping[str, object], new_pipeline: Mapping[str, object]
) -> set[str]:
    """Return changed global variable nodes for the first mutation increment.
    A variable whose value changes or disappears from the new definition is a
    changed node. Newly added variables are not yet modelled because they have
    no consumers in the old graph from which impact is selected.
    """
    old_variables = _global_variables(old_pipeline)
    new_variables = _global_variables(new_pipeline)

    return {
        name
        for name, value in old_variables.items()
        if name not in new_variables or new_variables[name] != value
    }

def _global_variables(pipeline: Mapping[str, object]) -> Mapping[str, object]:
    variables = pipeline.get("variables", {})
    if not isinstance(variables, Mapping):
        raise ValueError("GitLab global variables must be a mapping.")
    return variables
