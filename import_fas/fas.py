"""Compute a minimum feedback arc set with clingo."""

from __future__ import annotations

import clingo

from .graph import Edge, Graph

#: Drop as few edges as possible to make the graph acyclic. #edge is clingo's acyclicity
#: propagator: it rejects any model whose edges form a cycle.
ENCODING = """\
{ del(X,Y) } :- edge(X,Y).
#edge (X,Y) : edge(X,Y), not del(X,Y).
#minimize { 1,X,Y : del(X,Y) }.
#show del/2.
"""


def minimum_feedback_arc_set(graph: Graph) -> list[Edge]:
    """A smallest set of edges whose removal makes the graph acyclic."""
    if not graph.edges:
        return []
    ctl = clingo.Control(["--opt-strategy=usc"])
    ctl.add(
        "base",
        [],
        ENCODING + "".join(f"edge({src},{dst})." for src, dst in graph.edges),
    )
    ctl.ground([("base", [])])
    fas: list[Edge] = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            arguments = (x.arguments for x in model.symbols(shown=True))
            fas = [(a.number, b.number) for a, b in arguments]
        if not handle.get().exhausted:
            raise RuntimeError("clingo did not prove this set minimal")
    return sorted(fas)
