"""Format-independent selective analysis."""

from collections.abc import Mapping
from pathlib import Path

from capts.graph import select_affected_with_triggers
from capts.model import FormatAdapter


def select_changed_stages(
    adapter: FormatAdapter,
    before: str | Path | Mapping[str, str | Path],
    after: str | Path | Mapping[str, str | Path],
    *,
    pipeline_name: str = "main",
) -> set[str]:
    """Select stages affected by changes between two pipeline snapshots."""
    if isinstance(before, Mapping):
        model = adapter.parse(before)
    else:
        model = adapter.parse(before, pipeline_name=pipeline_name)

    events = adapter.detect_changes(before, after, pipeline_name=pipeline_name)
    return select_affected_with_triggers(model, events)
