import pytest

from capts.graph import build_graph
from capts.model import (
    ChangeEvent,
    ChangeType,
    EdgeInfo,
    EdgeType,
    ExecutionResult,
    NodeInfo,
    NodeType,
    PipelineModel,
)
from capts.risk import compute_risk_score, score_selected_stages


def test_risk_score_for_a_direct_local_removal() -> None:
    graph = build_graph(
        PipelineModel(
            nodes=[
                NodeInfo("BUILD_CMD", NodeType.VARIABLE, pipeline="main"),
                NodeInfo("main/release", NodeType.STAGE, pipeline="main"),
            ],
            edges=[EdgeInfo("main/release", "BUILD_CMD", EdgeType.CONSUMES)],
        )
    )

    score = compute_risk_score(
        graph,
        "BUILD_CMD",
        "main/release",
        ChangeEvent("BUILD_CMD", ChangeType.REMOVED),
    )

    assert score.overall == pytest.approx(70.0)
    assert score.level == "HIGH"
    assert score.critical_path == 1.0
    assert score.fan_out == 0.0
    assert score.directness == 1.0
    assert score.change_severity == 1.0
    assert score.cross_pipeline == 0.0


def test_risk_scores_reflect_fan_out_and_cross_pipeline_impact() -> None:
    graph = build_graph(
        PipelineModel(
            nodes=[
                NodeInfo("FEATURE_FLAGS", NodeType.VARIABLE, pipeline="main"),
                NodeInfo("main/build", NodeType.STAGE, pipeline="main"),
                NodeInfo("deploy/test", NodeType.STAGE, pipeline="deploy"),
            ],
            edges=[
                EdgeInfo("main/build", "FEATURE_FLAGS", EdgeType.CONSUMES),
                EdgeInfo("deploy/test", "FEATURE_FLAGS", EdgeType.CONSUMES),
                EdgeInfo("deploy/test", "main/build", EdgeType.DEPENDS_ON),
            ],
        )
    )
    change = ChangeEvent("FEATURE_FLAGS", ChangeType.RENAMED)

    local_score = compute_risk_score(graph, "FEATURE_FLAGS", "main/build", change)
    cross_pipeline_score = compute_risk_score(
        graph, "FEATURE_FLAGS", "deploy/test", change
    )

    assert local_score.overall == pytest.approx(58.0)
    assert local_score.level == "HIGH"
    assert (local_score.critical_path, local_score.fan_out, local_score.cross_pipeline) == (
        0.0,
        1.0,
        0.0,
    )
    assert cross_pipeline_score.overall == pytest.approx(78.0)
    assert cross_pipeline_score.level == "CRITICAL"
    assert (
        cross_pipeline_score.critical_path,
        cross_pipeline_score.fan_out,
        cross_pipeline_score.cross_pipeline,
    ) == (1.0, 0.0, 1.0)


def test_score_selected_stages_attaches_independent_risks() -> None:
    graph = build_graph(
        PipelineModel(
            nodes=[
                NodeInfo("FEATURE_FLAGS", NodeType.VARIABLE, pipeline="main"),
                NodeInfo("main/build", NodeType.STAGE, pipeline="main"),
                NodeInfo("deploy/test", NodeType.STAGE, pipeline="deploy"),
            ],
            edges=[
                EdgeInfo("main/build", "FEATURE_FLAGS", EdgeType.CONSUMES),
                EdgeInfo("deploy/test", "FEATURE_FLAGS", EdgeType.CONSUMES),
                EdgeInfo("deploy/test", "main/build", EdgeType.DEPENDS_ON),
            ],
        )
    )

    scored_stages = score_selected_stages(
        graph,
        ChangeEvent("FEATURE_FLAGS", ChangeType.RENAMED),
        {"main/build", "deploy/test"},
    )

    assert [(stage.stage_id, stage.risk.overall) for stage in scored_stages] == [
        ("deploy/test", pytest.approx(78.0)),
        ("main/build", pytest.approx(58.0)),
    ]
    assert all(stage.execution_result is None for stage in scored_stages)


def test_execution_result_does_not_change_selected_stage_risk() -> None:
    graph = build_graph(
        PipelineModel(
            nodes=[
                NodeInfo("BUILD_CMD", NodeType.VARIABLE, pipeline="main"),
                NodeInfo("main/release", NodeType.STAGE, pipeline="main"),
            ],
            edges=[EdgeInfo("main/release", "BUILD_CMD", EdgeType.CONSUMES)],
        )
    )
    change = ChangeEvent("BUILD_CMD", ChangeType.REMOVED)

    passing = score_selected_stages(
        graph, change, {"main/release"}, [ExecutionResult("main/release", 0)]
    )[0]
    failing = score_selected_stages(
        graph, change, {"main/release"}, [ExecutionResult("main/release", 1)]
    )[0]

    assert passing.risk == failing.risk
    assert passing.execution_result is not None and passing.execution_result.passed
    assert failing.execution_result is not None and not failing.execution_result.passed
