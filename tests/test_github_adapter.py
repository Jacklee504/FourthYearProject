from pathlib import Path

from capts.adapters.github import GitHubActionsAdapter
from capts.graph import build_graph, select_affected_stages
from capts.model import EdgeType, NodeType


def test_github_poc_jobs_map_to_universal_model(tmp_path: Path) -> None:
    ci = tmp_path / "ci.yml"
    ci.write_text(
        """env:
  BUILD_ARGS: "--optimize --cache"
  TEST_FLAGS: "--verbose --coverage"
jobs:
  build:
    steps:
      - run: bash scripts/build.sh
        env:
          BUILD_ARGS: ${{ env.BUILD_ARGS }}
  test:
    needs: [build]
    uses: ./.github/workflows/run-tests.yml
    with:
      test_flags: ${{ env.TEST_FLAGS }}
      script: scripts/run_tests.py
  security:
    env:
      BUILD_ARGS: "--security-only"
    steps:
      - run: bash scripts/scan.sh
""",
        encoding="utf-8",
    )
    deploy = tmp_path / "deploy.yml"
    deploy.write_text(
        """env:
  TEST_FLAGS: "--smoke --quick"
jobs:
  smoke-test:
    uses: ./.github/workflows/run-tests.yml
    with:
      test_flags: ${{ env.TEST_FLAGS }}
      script: scripts/run_tests.py
""",
        encoding="utf-8",
    )

    model = GitHubActionsAdapter().parse({"ci": ci, "deploy": deploy})
    nodes = {node.id: node.node_type for node in model.nodes}
    edges = {(edge.source, edge.target, edge.edge_type) for edge in model.edges}

    assert nodes["ci/test"] == NodeType.STAGE
    assert nodes["deploy/smoke-test"] == NodeType.STAGE
    assert nodes["TEST_FLAGS"] == NodeType.VARIABLE
    assert nodes[".github/workflows/run-tests.yml"] == NodeType.TEMPLATE
    assert nodes["scripts/run_tests.py"] == NodeType.SCRIPT
    assert ("ci/test", "ci/build", EdgeType.DEPENDS_ON) in edges
    assert ("ci/build", "BUILD_ARGS", EdgeType.CONSUMES) in edges
    assert ("ci/security", "BUILD_ARGS", EdgeType.CONSUMES) not in edges
    assert ("ci/test", ".github/workflows/run-tests.yml", EdgeType.INHERITS) in edges
    assert ("ci/test", "scripts/run_tests.py", EdgeType.EXECUTES) in edges
    assert select_affected_stages(build_graph(model), {"TEST_FLAGS"}) == {
        "ci/test", "deploy/smoke-test"
    }


def test_github_vars_and_secrets_references_are_variable_nodes(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "jobs:\n  build:\n    steps:\n      - run: echo '${{ vars.MODE }} ${{ secrets.TOKEN }}'\n",
        encoding="utf-8",
    )

    model = GitHubActionsAdapter().parse(workflow, pipeline_name="ci")

    assert {(edge.source, edge.target, edge.edge_type) for edge in model.edges} == {
        ("ci/build", "vars.MODE", EdgeType.CONSUMES),
        ("ci/build", "secrets.TOKEN", EdgeType.CONSUMES),
    }
