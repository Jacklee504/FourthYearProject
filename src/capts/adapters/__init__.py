"""Adapters that map CI formats into the CAPTS dependency graph."""
from pathlib import Path

from capts.adapters.github import GitHubActionsAdapter
from capts.adapters.gitlab import GitLabAdapter


def detect_format(directory: Path) -> GitLabAdapter | GitHubActionsAdapter:
    """Return the adapter for a supported pipeline directory."""
    for adapter_class in (GitLabAdapter, GitHubActionsAdapter):
        if adapter_class.detect(directory):
            return adapter_class()
    raise ValueError(f"Could not detect a supported pipeline format in {directory}")
