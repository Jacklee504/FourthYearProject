"""CLI Interface for CAPTS"""
import argparse
from pathlib import Path
import yaml

from capts.adapters.gitlab import parse_gitlab_pipeline
from capts.diff import detect_changed_nodes
from capts.graph import select_affected_stages

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--pipeline-name", default="main")
    args = parser.parse_args(argv)

    with Path(args.before).open(encoding="utf-8") as file:
        before = yaml.safe_load(file) or {}
    with Path(args.after).open(encoding="utf-8") as file:
        after = yaml.safe_load(file) or {}

    graph = parse_gitlab_pipeline(args.before, pipeline_name=args.pipeline_name)
    changed = detect_changed_nodes(before, after)

    for stage in sorted(select_affected_stages(graph, changed)):
        print(stage)

    return 0