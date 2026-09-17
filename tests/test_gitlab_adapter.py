from pathlib import Path
from capts.adapters.gitlab import GitLabAdapter, parse_gitlab_pipeline
from capts.graph import select_affected_stages
from capts.model import EdgeType, NodeType

FIXTURE = Path(__file__).parent / "fixtures" / "simple.gitlab-ci.yml"

def test_gitlab_adapter_returns_a_pipeline_model() -> None:
    model = GitLabAdapter().parse(FIXTURE, pipeline_name="main")

    assert {(node.id, node.node_type) for node in model.nodes} == {
        ("APP_MODE", NodeType.VARIABLE),
        ("main/build", NodeType.STAGE),
        ("main/test", NodeType.STAGE),
    }
    assert {(edge.source, edge.target, edge.edge_type) for edge in model.edges} == {
        ("main/build", "APP_MODE", EdgeType.CONSUMES),
        ("main/test", "APP_MODE", EdgeType.CONSUMES),
        ("main/test", "main/build", EdgeType.DEPENDS_ON),
    }

def test_gitlab_adapter_maps_variables_jobs_and_needs() -> None:
    graph = parse_gitlab_pipeline(FIXTURE, pipeline_name="main")

    assert graph.nodes["APP_MODE"]["node_type"] == NodeType.VARIABLE
    assert graph.nodes["main/build"]["node_type"] == NodeType.STAGE
    assert graph.nodes["main/test"]["node_type"] == NodeType.STAGE
    assert graph.edges["main/build", "APP_MODE"]["edge_type"] == EdgeType.CONSUMES
    assert graph.edges["main/test", "main/build"]["edge_type"] == EdgeType.DEPENDS_ON

def test_gitlab_variable_change_selects_its_consuming_jobs() -> None:
    graph = parse_gitlab_pipeline(FIXTURE, pipeline_name="main")

    assert select_affected_stages(graph, {"APP_MODE"}) == {
        "main/build",
        "main/test",
    }


def test_gitlab_adapter_scans_the_full_job_and_honours_local_overrides(
    tmp_path: Path,
) -> None:
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text(
        """variables:
  BUILD_CMD: make all
  DEPLOY_ENV: production

build:
  script: $BUILD_CMD

security-scan:
  variables:
    BUILD_CMD: make scan
  script: $BUILD_CMD

deploy:
  rules:
    - if: '$DEPLOY_ENV == "production"'
  script: echo deploy
""",
        encoding="utf-8",
    )

    graph = parse_gitlab_pipeline(pipeline, pipeline_name="main")

    assert graph.has_edge("main/build", "BUILD_CMD")
    assert not graph.has_edge("main/security-scan", "BUILD_CMD")
    assert graph.has_edge("main/deploy", "DEPLOY_ENV")
