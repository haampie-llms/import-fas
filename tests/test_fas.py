import random

from import_fas import Graph, is_acyclic, minimum_feedback_arc_set


def test_an_empty_graph():
    assert minimum_feedback_arc_set(Graph([], [])) == []


def test_nodes_without_edges():
    assert minimum_feedback_arc_set(Graph(["a", "b"], [])) == []


def test_a_dag_needs_no_removals():
    assert (
        minimum_feedback_arc_set(Graph(["a", "b", "c"], [(0, 1), (1, 2), (0, 2)])) == []
    )


def test_a_cycle_costs_one_edge():
    graph = Graph(["a", "b", "c"], [(0, 1), (1, 2), (2, 0)])
    fas = minimum_feedback_arc_set(graph)
    assert len(fas) == 1
    assert set(fas) <= set(graph.edges)
    assert is_acyclic(graph, fas)


def test_disjoint_cycles_cost_one_edge_each():
    graph = Graph(list("abcdef"), [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3)])
    assert len(minimum_feedback_arc_set(graph)) == 2


def test_cycles_sharing_an_edge_cost_one_edge():
    """Both cycles run through a -> b, so deleting that one edge is enough."""
    graph = Graph(list("abcd"), [(0, 1), (1, 2), (2, 0), (1, 3), (3, 0)])
    assert minimum_feedback_arc_set(graph) == [(0, 1)]


def test_the_result_always_breaks_every_cycle():
    rng = random.Random(0)
    for _ in range(20):
        n = rng.randint(2, 8)
        edges = sorted(
            {
                (i, j)
                for i in range(n)
                for j in range(n)
                if i != j and rng.random() < 0.4
            }
        )
        graph = Graph([str(i) for i in range(n)], edges)
        assert is_acyclic(graph, minimum_feedback_arc_set(graph))
