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

def test_gitlab_adapter_maps_referenced_templates(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text(
        """.base:
  image: python:3.12

.test-base:
  image: python:3.12

.unused:
  image: python:3.12

unit-test:
  extends: .test-base

quality-check:
  extends:
    - .base
    - .test-base
""",
        encoding="utf-8",
    )

    model = GitLabAdapter().parse(pipeline, pipeline_name="main")

    assert {(node.id, node.node_type) for node in model.nodes} == {
        ("main/unit-test", NodeType.STAGE),
        ("main/quality-check", NodeType.STAGE),
        ("main/.base", NodeType.TEMPLATE),
        ("main/.test-base", NodeType.TEMPLATE),
    }
    assert {(edge.source, edge.target, edge.edge_type) for edge in model.edges} == {
        ("main/unit-test", "main/.test-base", EdgeType.INHERITS),
        ("main/quality-check", "main/.base", EdgeType.INHERITS),
        ("main/quality-check", "main/.test-base", EdgeType.INHERITS),
    }

def test_gitlab_adapter_maps_script_references(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text(
        """test:
  script:
    - python scripts/test.py --fast
    - scripts/check.py
    - echo complete

lint:
  script: scripts/test.py
""",
        encoding="utf-8",
    )

    model = GitLabAdapter().parse(pipeline, pipeline_name="main")

    assert {
        node.id for node in model.nodes if node.node_type == NodeType.SCRIPT
    } == {"scripts/test.py", "scripts/check.py"}
    assert {(edge.source, edge.target, edge.edge_type) for edge in model.edges} == {
        ("main/test", "scripts/test.py", EdgeType.EXECUTES),
        ("main/test", "scripts/check.py", EdgeType.EXECUTES),
        ("main/lint", "scripts/test.py", EdgeType.EXECUTES),
    }

def test_gitlab_adapter_combines_explicit_pipeline_files(tmp_path: Path) -> None:
    main = tmp_path / "main.yml"
    deploy = tmp_path / "deploy.yml"
    canary = tmp_path / "canary.yml"
    notify = tmp_path / "notify.yml"
    main.write_text(
        """variables:
  SHARED_VALUE: value

.base:
  image: python:3.12

build:
  extends: .base
  script: python scripts/shared.py $SHARED_VALUE

gate:
  trigger:
    include:
      - local: deploy.yml
      - local: canary.yml
""",
        encoding="utf-8",
    )
    deploy.write_text(
        """.base:
  image: python:3.12

build:
  extends: .base
  script: python scripts/shared.py $SHARED_VALUE

deploy-prod:
  needs: [build]
  trigger:
    include:
      - local: notify.yml
""",
        encoding="utf-8",
    )
    canary.write_text(
        """.base:
  image: python:3.12

build:
  extends: .base
  script: python scripts/shared.py
""",
        encoding="utf-8",
    )
    notify.write_text(
        """.base:
  image: python:3.12

send-notification:
  extends: .base
  script: python scripts/shared.py $SHARED_VALUE
""",
        encoding="utf-8",
    )

    model = GitLabAdapter().parse({
        "main": main,
        "deploy": deploy,
        "canary": canary,
        "notify": notify,
    })

    assert {(node.id, node.node_type) for node in model.nodes} >= {
        ("main/build", NodeType.STAGE),
        ("deploy/build", NodeType.STAGE),
        ("main/.base", NodeType.TEMPLATE),
        ("deploy/.base", NodeType.TEMPLATE),
        ("SHARED_VALUE", NodeType.VARIABLE),
        ("scripts/shared.py", NodeType.SCRIPT),
    }
    assert [node.id for node in model.nodes].count("SHARED_VALUE") == 1
    assert [node.id for node in model.nodes].count("scripts/shared.py") == 1
    assert {(edge.source, edge.target, edge.edge_type) for edge in model.edges} >= {
        ("deploy/build", "SHARED_VALUE", EdgeType.CONSUMES),
        ("notify/send-notification", "SHARED_VALUE", EdgeType.CONSUMES),
        ("main/build", "main/.base", EdgeType.INHERITS),
        ("deploy/build", "deploy/.base", EdgeType.INHERITS),
        ("main/build", "scripts/shared.py", EdgeType.EXECUTES),
        ("deploy/deploy-prod", "deploy/build", EdgeType.DEPENDS_ON),
    }
    assert model.triggers == {
        "main/gate": {"deploy/build", "deploy/deploy-prod", "canary/build"},
        "deploy/deploy-prod": {"notify/send-notification"},
    }
