"""Compute a minimum feedback arc set with clingo."""

from __future__ import annotations

import clingo

from .graph import Edge, Graph

#: Drop as few edges as possible to make the graph acyclic. #edge is clingo's acyclicity
#: propagator: it rejects any model whose edges form a cycle. An edge from a package to
#: one of its own submodules is fixed: the point of the package is to expose the
#: submodule, so dropping that import is not a real option. A cycle cannot consist of
#: fixed edges alone, since names strictly lengthen along one, so a model always exists.
ENCODING = """\
{ del(X,Y) } :- edge(X,Y), not fixed(X,Y).
#edge (X,Y) : edge(X,Y), not del(X,Y).
#minimize { 1,X,Y : del(X,Y) }.
#show del/2.
"""


def minimum_feedback_arc_set(graph: Graph) -> list[Edge]:
    """A smallest set of edges whose removal makes the graph acyclic."""
    if not graph.edges:
        return []
    ctl = clingo.Control(["--opt-strategy=usc"])
    facts = "".join(f"edge({src},{dst})." for src, dst in graph.edges)
    facts += "".join(
        f"fixed({src},{dst})."
        for src, dst in graph.edges
        if graph.nodes[dst].startswith(f"{graph.nodes[src]}.")
    )
    ctl.add("base", [], ENCODING + facts)
    ctl.ground([("base", [])])
    fas: list[Edge] = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            arguments = (x.arguments for x in model.symbols(shown=True))
            fas = [(a.number, b.number) for a, b in arguments]
        if not handle.get().exhausted:
            raise RuntimeError("clingo did not prove this set minimal")
    return sorted(fas)
