"""Report the import statements that have to go to make a package's import graph acyclic."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable

from .fas import minimum_feedback_arc_set
from .graph import Edge, Graph, build_graph
from .io import FORMATS, read_graph, write_graph

BOLD, RED, GREEN, GREY = "1", "31", "32", "90"


def colorize(text: str, *codes: str) -> str:
    if "NO_COLOR" in os.environ:
        return text
    if not (sys.stdout.isatty() or "GITHUB_ACTIONS" in os.environ):
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def plural(n: int, word: str) -> str:
    return word if n == 1 else f"{word}s"


def display(path: str) -> str:
    """A path relative to the working directory when that is inside it, else as is."""
    try:
        relative = os.path.relpath(path)
    except ValueError:  # another drive on Windows
        return path
    return path if relative.startswith("..") else relative


def lines(graph: Graph, edges: Iterable[Edge]) -> list[str]:
    """One ``path:line: imports module`` line per import statement behind the given edges,
    in file order; ``module: imports module`` for a graph that has no locations."""
    keyed: list[tuple[tuple[str, int, str], str]] = []
    for edge in edges:
        src, dst = graph.names([edge])[0]
        where = graph.locations.get(edge)
        if not where:
            keyed.append(((src, 0, dst), f"{src}: imports {dst}"))
        for path, line in where or ():
            shown = display(path)
            keyed.append(((shown, line, dst), f"{shown}:{line}: imports {dst}"))
    return [text for _, text in sorted(keyed)]


def print_lines(graph: Graph, edges: Iterable[Edge], *codes: str) -> None:
    for line in lines(graph, edges):
        print(colorize(line, *codes))


def compare(old: Graph, new: Graph) -> int:
    """Print the import statements this change added to the solution, and the count."""
    old_fas = minimum_feedback_arc_set(old)
    new_fas = minimum_feedback_arc_set(new)
    before, after = len(old_fas), len(new_fas)
    difference = after - before

    if difference <= 0:
        print_lines(new, new_fas, GREY)
        if difference == 0:
            summary = f"imports to remove unchanged at {after}"
        else:
            summary = f"imports to remove decreased from {before} to {after}"
        print(colorize(summary, GREEN, BOLD))
        return 0

    # Solve the new graph again without the edges the old solution already blamed, so what is
    # left to blame is what this change introduced. A heuristic: the old solution is not
    # necessarily a subset of the new graph's edges.
    excluded = set(new.indices(old.names(old_fas)))
    blamed = minimum_feedback_arc_set(
        Graph(new.nodes, [e for e in new.edges if e not in excluded], new.locations)
    )
    print_lines(new, blamed, RED)

    # Breaking exactly those is not necessarily the cheapest way back to the old count.
    if len(blamed) > difference:
        print(f"removing any {difference} of the following would undo the increase:")
        print_lines(new, new_fas, GREY)
    print(colorize(f"imports to remove increased from {before} to {after}", RED, BOLD))
    return 1


def load(
    path: str, exclude: str | None, inline: bool, parser: argparse.ArgumentParser
) -> Graph:
    """A package directory to analyze, or a graph file dumped earlier."""
    if os.path.isdir(path):
        return build_graph(path, exclude, inline)
    if exclude is not None or inline:
        parser.error(f"--exclude and --inline do not apply to a graph file: {path}")
    with open(path, encoding="utf-8") as f:
        return read_graph(f)


def add_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("package", metavar="PACKAGE_DIR_OR_GRAPH")
    parser.add_argument(
        "--exclude",
        metavar="REGEX",
        help="regex searched in module names to leave out of the graph; a package that "
        "matches is pruned along with everything under it",
    )
    parser.add_argument(
        "--inline",
        action="store_true",
        help="include imports inside functions and classes",
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="import-fas", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser("graph", help="dump the import graph the solver sees")
    add_source(dump)
    dump.add_argument(
        "-o", "--output", default="-", help="output file, - for stdout (default)"
    )
    dump.add_argument(
        "-f", "--format", choices=FORMATS, help="default: from -o, else json"
    )

    add_source(sub.add_parser("solve", help="report the imports that break all cycles"))

    cmp_parser = sub.add_parser(
        "compare", help="fail if the new tree needs more removals"
    )
    cmp_parser.add_argument("old", metavar="OLD")
    cmp_parser.add_argument("new", metavar="NEW")
    cmp_parser.add_argument("--exclude", metavar="REGEX")
    cmp_parser.add_argument("--inline", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "graph":
            graph = load(args.package, args.exclude, args.inline, parser)
            format = args.format or ("text" if args.output.endswith(".txt") else "json")
            if args.output == "-":
                write_graph(graph, sys.stdout, format)
            else:
                with open(args.output, "w", encoding="utf-8") as f:
                    write_graph(graph, f, format)
            return 0

        if args.command == "solve":
            graph = load(args.package, args.exclude, args.inline, parser)
            fas = minimum_feedback_arc_set(graph)
            print_lines(graph, fas, GREY)
            print(colorize(f"{len(fas)} {plural(len(fas), 'import')} to remove", BOLD))
            return 0

        old = load(args.old, args.exclude, args.inline, parser)
        new = load(args.new, args.exclude, args.inline, parser)
        return compare(old, new)
    except (OSError, SyntaxError, ValueError) as e:
        print(f"import-fas: {e}", file=sys.stderr)
        return 2
