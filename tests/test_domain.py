"""领域层测试。"""

import pytest

from knowledge_path_demo.domain import (
    GraphInvalidError,
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    MasteryLevel,
    build_path_order,
    compute_gaps,
    is_gap,
    validate_graph,
)


def _g(nodes, edges):
    return KnowledgeGraph(
        nodes=tuple(KnowledgeNode(id=i, title=i) for i in nodes),
        edges=tuple(KnowledgeEdge(from_id=a, to_id=b) for a, b in edges),
    )


def test_is_gap_threshold():
    assert is_gap(MasteryLevel.unknown)
    assert is_gap(MasteryLevel.heard)
    assert not is_gap(MasteryLevel.understood)
    assert not is_gap(MasteryLevel.expert)


def test_validate_rejects_cycle():
    g = _g(["a", "b"], [("a", "b"), ("b", "a")])
    with pytest.raises(GraphInvalidError) as ei:
        validate_graph(g)
    assert "环" in str(ei.value)


def test_validate_rejects_too_many_nodes():
    nodes = [f"n{i}" for i in range(5)]
    g = _g(nodes, [])
    with pytest.raises(GraphInvalidError):
        validate_graph(g, max_nodes=3)


def test_validate_ok_dag():
    g = _g(["a", "b", "c"], [("a", "b"), ("b", "c")])
    validate_graph(g)


def test_path_order_respects_prereq():
    g = _g(["a", "b", "c"], [("a", "b"), ("b", "c")])
    mastery = {
        "a": MasteryLevel.unknown,
        "b": MasteryLevel.unknown,
        "c": MasteryLevel.unknown,
    }
    order = build_path_order(g, mastery)
    assert order.index("a") < order.index("b") < order.index("c")


def test_path_skips_mastered_prereq():
    g = _g(["a", "b", "c"], [("a", "b"), ("b", "c")])
    mastery = {
        "a": MasteryLevel.proficient,
        "b": MasteryLevel.unknown,
        "c": MasteryLevel.unknown,
    }
    order = build_path_order(g, mastery)
    assert "a" not in order
    assert order.index("b") < order.index("c")


def test_compute_gaps():
    gaps = compute_gaps(
        ["a", "b"],
        {"a": MasteryLevel.heard, "b": MasteryLevel.understood},
    )
    assert gaps == ["a"]
