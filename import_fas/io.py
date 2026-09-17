"""Read and write import graphs and their feedback arc sets."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TextIO

from .graph import Edge, Graph

#: the graph file formats, see the README
FORMATS = ("json", "text")


def write_graph(graph: Graph, f: TextIO, format: str = "json") -> None:
    if format == "json":
        json.dump(
            {"nodes": graph.nodes, "edges": [list(edge) for edge in graph.edges]}, f
        )
        f.write("\n")
    elif format == "text":
        print(len(graph.nodes), file=f)
        for node in graph.nodes:
            print(node, file=f)
        print(len(graph.edges), file=f)
        for src, dst in graph.edges:
            print(src, dst, file=f)
    else:
        raise ValueError(f"unknown graph format: {format}")


def read_graph(f: TextIO) -> Graph:
    """Read a graph in either format; the first character tells them apart."""
    text = f.read()
    if text.lstrip().startswith("{"):
        data = json.loads(text)
        return Graph(list(data["nodes"]), [(int(a), int(b)) for a, b in data["edges"]])
    words = text.split()
    if not words or not words[0].isdigit():
        raise ValueError(
            "not a graph file: expected json, or a node count on the first line"
        )
    node_count = int(words[0])
    nodes = words[1 : 1 + node_count]
    try:
        edge_count = int(words[1 + node_count])
        numbers = [
            int(x) for x in words[2 + node_count : 2 + node_count + 2 * edge_count]
        ]
    except (IndexError, ValueError):
        raise ValueError(
            f"truncated graph file: it declares {node_count} nodes"
        ) from None
    if len(numbers) != 2 * edge_count:
        raise ValueError(f"truncated graph file: it declares {edge_count} edges")
    return Graph(nodes, list(zip(numbers[::2], numbers[1::2])))


def write_fas(fas: Sequence[Edge], f: TextIO) -> None:
    for src, dst in fas:
        print(src, dst, file=f)


def read_fas(f: TextIO, graph: Graph) -> list[Edge]:
    """One ``src dst`` pair of node indices per line; # starts a comment."""
    edges = set(graph.edges)
    fas = []
    for number, line in enumerate(f, 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            src, dst = (int(x) for x in line.split())
        except ValueError:
            raise ValueError(
                f"line {number}: expected two node indices, got {line!r}"
            ) from None
        if (src, dst) not in edges:
            raise ValueError(f"line {number}: {src} {dst} is not an edge of this graph")
        fas.append((src, dst))
    return sorted(fas)
