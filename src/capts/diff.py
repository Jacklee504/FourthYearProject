"""Compatibility helper for mapping change events to graph node IDs."""
from collections.abc import Mapping

from capts.adapters.gitlab import GitLabAdapter


def detect_changed_nodes(
    old_pipeline: Mapping[str, object], new_pipeline: Mapping[str, object]
) -> set[str]:
    """Return node IDs reported by the GitLab change detector."""
    return {
        event.node_id
        for event in GitLabAdapter().detect_changes(old_pipeline, new_pipeline)
    }
