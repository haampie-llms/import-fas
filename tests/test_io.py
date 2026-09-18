import io

import pytest

from import_fas import Graph, read_graph, write_graph

GRAPH = Graph(["pkg", "pkg.a", "pkg.b", "pkg.lonely"], [(0, 1), (1, 2), (2, 1)])


@pytest.mark.parametrize("format", ["json", "text"])
def test_a_graph_survives_a_round_trip(format):
    f = io.StringIO()
    write_graph(GRAPH, f, format)
    back = read_graph(io.StringIO(f.getvalue()))
    assert back == GRAPH
    assert back.locations == {}


def test_the_json_format():
    f = io.StringIO()
    write_graph(GRAPH, f, "json")
    assert f.getvalue() == (
        '{"nodes": ["pkg", "pkg.a", "pkg.b", "pkg.lonely"], '
        '"edges": [[0, 1], [1, 2], [2, 1]]}\n'
    )


def test_the_text_format():
    f = io.StringIO()
    write_graph(GRAPH, f, "text")
    assert f.getvalue() == "4\npkg\npkg.a\npkg.b\npkg.lonely\n3\n0 1\n1 2\n2 1\n"


def test_leading_whitespace_does_not_confuse_the_format_detection():
    assert read_graph(io.StringIO('\n  {"nodes": ["a"], "edges": []}')) == Graph(
        ["a"], []
    )


def test_an_unknown_format():
    with pytest.raises(ValueError, match="unknown graph format"):
        write_graph(GRAPH, io.StringIO(), "dot")


def test_a_truncated_text_graph():
    with pytest.raises(ValueError, match="truncated"):
        read_graph(io.StringIO("3\na\nb\n"))


def test_a_file_that_is_not_a_graph():
    with pytest.raises(ValueError, match="not a graph file"):
        read_graph(io.StringIO("hello there\n"))
