"""CLI Interface for CAPTS"""
import argparse

from capts.adapters.gitlab import GitLabAdapter
from capts.core import select_changed_stages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--pipeline-name", default="main")
    args = parser.parse_args(argv)

    selected = select_changed_stages(
        GitLabAdapter(),
        args.before,
        args.after,
        pipeline_name=args.pipeline_name,
    )

    for stage in sorted(selected):
        print(stage)

    return 0
