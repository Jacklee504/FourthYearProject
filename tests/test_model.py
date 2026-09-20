from capts.adapters.gitlab import GitLabAdapter
from capts.model import (
    ChangeEvent,
    ChangeType,
    EdgeInfo,
    EdgeType,
    ExecutionResult,
    FormatAdapter,
    NodeInfo,
    NodeType,
    PipelineModel,
)


def test_model_labels_are_stable_strings() -> None:
    assert NodeType.STAGE == "stage"
    assert NodeType.VARIABLE == "variable"
    assert NodeType.TEMPLATE == "template"
    assert NodeType.SCRIPT == "script"
    assert EdgeType.CONSUMES == "consumes"
    assert EdgeType.INHERITS == "inherits"
    assert EdgeType.DEPENDS_ON == "depends_on"
    assert EdgeType.EXECUTES == "executes"
    assert ChangeType.ADDED == "added"
    assert ChangeType.REMOVED == "removed"
    assert ChangeType.MODIFIED == "modified"
    assert ChangeType.RENAMED == "renamed"


def test_pipeline_model_holds_nodes_edges_and_changes() -> None:
    model = PipelineModel(
        nodes=[NodeInfo("main/build", NodeType.STAGE, pipeline="main")],
        edges=[EdgeInfo("main/build", "BUILD_CMD", EdgeType.CONSUMES)],
    )
    change = ChangeEvent("BUILD_CMD", ChangeType.REMOVED)

    assert model.nodes[0].id == "main/build"
    assert model.edges[0].edge_type == EdgeType.CONSUMES
    assert change.change_type == ChangeType.REMOVED


def test_execution_result_reports_a_passing_stage() -> None:
    result = ExecutionResult("main/build", exit_code=0)

    assert result.stage_id == "main/build"
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.passed


def test_execution_result_reports_a_failing_stage() -> None:
    result = ExecutionResult("main/build", exit_code=1, stderr="build failed")

    assert result.stderr == "build failed"
    assert not result.passed


def test_gitlab_adapter_implements_the_format_adapter_contract() -> None:
    assert isinstance(GitLabAdapter(), FormatAdapter)
