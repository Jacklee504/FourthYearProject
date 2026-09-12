from capts.adapters.gitlab import GitLabAdapter
from capts.model import EdgeType, FormatAdapter, NodeType

def test_model_labels_are_stable_strings() -> None:
    assert NodeType.STAGE == "stage"
    assert NodeType.VARIABLE == "variable"
    assert NodeType.TEMPLATE == "template"
    assert NodeType.SCRIPT == "script"
    assert EdgeType.CONSUMES == "consumes"
    assert EdgeType.INHERITS == "inherits"
    assert EdgeType.DEPENDS_ON == "depends_on"
    assert EdgeType.EXECUTES == "executes"


def test_gitlab_adapter_implements_the_format_adapter_contract() -> None:
    assert isinstance(GitLabAdapter(), FormatAdapter)
