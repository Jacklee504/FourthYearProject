"""Compatibility helper for mapping change events to graph node IDs."""
import subprocess
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory

from capts.adapters.gitlab import GitLabAdapter
from capts.model import ChangeEvent, FormatAdapter


def detect_changed_nodes(
    old_pipeline: Mapping[str, object], new_pipeline: Mapping[str, object]
) -> set[str]:
    """Return node IDs reported by the GitLab change detector."""
    return {
        event.node_id
        for event in GitLabAdapter().detect_changes(old_pipeline, new_pipeline)
    }

def detect_ref_changes(
    adapter: FormatAdapter,
    repository: Path,
    revision_range: str,
    pipelines: Mapping[str, str | Path],
) -> list[ChangeEvent]:
    """Compare named pipeline files between two Git refs."""
    before, separator, after = revision_range.partition("..")
    if not separator or not before or not after:
        raise ValueError("Expected a Git range such as main..HEAD")

    def git(*args: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(f"Git command failed: {result.stderr.decode().strip()}")
        return result.stdout

    changed = set(git("diff", "--name-only", before, after, "--").decode().splitlines())
    pipeline_files = {str(path) for path in pipelines.values()}
    files = pipeline_files | {path for path in changed if path.startswith("scripts/")}

    with TemporaryDirectory() as temporary:
        old_root = Path(temporary) / "old"
        new_root = Path(temporary) / "new"
        for root, ref in ((old_root, before), (new_root, after)):
            for relative in sorted(files):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(git("show", f"{ref}:{relative}"))

        old_pipelines = {name: old_root / path for name, path in pipelines.items()}
        new_pipelines = {name: new_root / path for name, path in pipelines.items()}
        return adapter.detect_changes(old_pipelines, new_pipelines, old_script_root=old_root, new_script_root=new_root)

def detect_staged_changes(
    adapter: FormatAdapter,
    repository: Path,
    pipelines: Mapping[str, str | Path],
) -> list[ChangeEvent]:
    """Compare HEAD with the staged version of pipeline and script files."""
    def git(*args: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(f"Git command failed: {result.stderr.decode().strip()}")
        return result.stdout

    changed = set(git("diff", "--cached", "--name-only", "HEAD", "--").decode().splitlines())
    pipeline_files = {str(path) for path in pipelines.values()}
    files = pipeline_files | {path for path in changed if path.startswith("scripts/")}

    with TemporaryDirectory() as temporary:
        old_root = Path(temporary) / "old"
        new_root = Path(temporary) / "new"
        for relative in sorted(files):
            for root, version in (
                (old_root, f"HEAD:{relative}"),
                (new_root, f":{relative}")
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(git("show", version))

        old_pipelines = {name: old_root / path for name, path in pipelines.items()}
        new_pipelines = {name: new_root / path for name, path in pipelines.items()}
        return adapter.detect_changes(old_pipelines, new_pipelines, old_script_root=old_root, new_script_root=new_root)

def detect_unstaged_changes(
    adapter: FormatAdapter,
    repository: Path,
    pipelines: Mapping[str, str | Path],
) -> list[ChangeEvent]:
    """Compare indexed files with their working-tree versions."""
    def git(*args: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(f"Git command failed: {result.stderr.decode().strip()}")
        return result.stdout

    changed = set(git("diff", "--name-only", "--").decode().splitlines())
    pipeline_files = {str(path) for path in pipelines.values()}
    files = pipeline_files | {path for path in changed if path.startswith("scripts/")}

    with TemporaryDirectory() as temporary:
        old_root = Path(temporary) / "old"
        new_root = Path(temporary) / "new"
        for relative in sorted(files):
            old_path = old_root / relative
            old_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.write_bytes(git("show", f":{relative}"))

            new_path = new_root / relative
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_path.write_bytes((repository / relative).read_bytes())

        old_pipelines = {name: old_root / path for name, path in pipelines.items()}
        new_pipelines = {name: new_root / path for name, path in pipelines.items()}
        return adapter.detect_changes(
            old_pipelines,
            new_pipelines,
            old_script_root=old_root,
            new_script_root=new_root,
        )