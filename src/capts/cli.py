"""CLI Interface for CAPTS"""
import argparse

from capts.adapters.gitlab import GitLabAdapter
from capts.graph import build_graph, select_affected_stages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--pipeline-name", default="main")
    args = parser.parse_args(argv)

    adapter = GitLabAdapter()
    graph = build_graph(adapter.parse(args.before, pipeline_name=args.pipeline_name))
    changed = {
        event.node_id
        for event in adapter.detect_changes(
            args.before, args.after, pipeline_name=args.pipeline_name
        )
    }

    for stage in sorted(select_affected_stages(graph, changed)):
        print(stage)

    return 0
