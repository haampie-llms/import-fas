import graphlib
import random

from uncycle import Graph, build_graph, minimum_feedback_arc_set


def is_acyclic(graph, removed=()):
    skip = set(removed)
    predecessors = {i: [] for i in range(len(graph.nodes))}
    for src, dst in graph.edges:
        if (src, dst) not in skip:
            predecessors[dst].append(src)
    try:
        graphlib.TopologicalSorter(predecessors).prepare()
    except graphlib.CycleError:
        return False
    return True


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


def test_a_re_exported_import_is_cut_once(tree):
    """pkg exposes pkg.y, which imports pkg.foo, which imports three modules that import
    pkg. One statement in pkg/y.py breaks every cycle; the re-export in pkg never counts."""
    d = tree(
        {
            "pkg/__init__.py": "from . import y",
            "pkg/y.py": "import pkg.foo",
            "pkg/foo.py": "import pkg.a\nimport pkg.b\nimport pkg.c",
            "pkg/a.py": "import pkg",
            "pkg/b.py": "import pkg",
            "pkg/c.py": "import pkg",
        }
    )
    graph = build_graph(d)
    assert graph.names(minimum_feedback_arc_set(graph)) == [("pkg.y", "pkg.foo")]


def test_a_package_never_drops_the_import_of_its_own_submodule(tree):
    d = tree({"pkg/__init__.py": "from . import y", "pkg/y.py": "import pkg"})
    graph = build_graph(d)
    assert graph.names(minimum_feedback_arc_set(graph)) == [("pkg.y", "pkg")]
