from capts.model import EdgeType, NodeType


def test_model_labels_are_stable_strings() -> None:
    assert NodeType.STAGE == "stage"
    assert NodeType.VARIABLE == "variable"
    assert EdgeType.CONSUMES == "consumes"
    assert EdgeType.DEPENDS_ON == "depends_on"


if __name__ == '__main__':
    unittest.main()
