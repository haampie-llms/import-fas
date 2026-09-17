"""Report the import statements that have to go to make a package's import graph acyclic."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Sequence

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


def print_edges(graph: Graph, fas: Iterable[Edge], *codes: str) -> None:
    grouped: dict[str, list[str]] = {}
    for src, dst in graph.names(fas):
        grouped.setdefault(src, []).append(dst)
    for src in sorted(grouped):
        targets = ", ".join(sorted(grouped[src]))
        print(colorize(f"{src.replace('.', '/')} imports: {targets}", *codes))


def print_solution(graph: Graph, fas: Sequence[Edge]) -> None:
    header = (
        "\nAll import cycles are broken by removing the following import statements:"
    )
    print(colorize(header, GREY))
    print("---")
    print_edges(graph, fas, GREY)
    print("---")


def compare(old: Graph, new: Graph) -> int:
    """Print how the number of problematic imports changed, and blame the new ones."""
    old_fas = minimum_feedback_arc_set(old)
    new_fas = minimum_feedback_arc_set(new)
    before, after = len(old_fas), len(new_fas)
    difference = after - before

    count = "The overall number of problematic import statements"
    if difference == 0:
        summary = f"{count} stayed the same: {after}"
    elif difference < 0:
        summary = f"{count} decreased by {-difference} from {before} to {after}"
    else:
        summary = f"{count} increased by {difference} from {before} to {after}"
    print(colorize(summary, RED if difference > 0 else GREEN, BOLD), end=".")

    if difference <= 0:
        print()
        if after:
            print_solution(new, new_fas)
        return 0

    # Solve the new graph again without the edges the old solution already blamed, so what is
    # left to blame is what this change introduced. A heuristic: the old solution is not
    # necessarily a subset of the new graph's edges.
    excluded = set(new.indices(old.names(old_fas)))
    blamed = minimum_feedback_arc_set(
        Graph(new.nodes, [e for e in new.edges if e not in excluded])
    )
    statements = plural(len(blamed), "statement")
    print(
        f" This is likely a direct consequence of the following import {statements}:\n"
    )
    print_edges(new, blamed, RED)

    # Breaking exactly those is not necessarily the cheapest way back to the old count.
    if len(blamed) > difference:
        print(
            f"\nHowever, instead of removing {len(blamed)} import {statements}, it is "
            f"sufficient to remove only {difference} import "
            f"{plural(difference, 'statement')} from the following list:\n"
        )
        print("---")
        print_edges(new, new_fas)
        print("---")
    else:
        print_solution(new, new_fas)
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
            print(f"{len(fas)} problematic import {plural(len(fas), 'statement')}")
            if fas:
                print_solution(graph, fas)
            return 0

        old = load(args.old, args.exclude, args.inline, parser)
        new = load(args.new, args.exclude, args.inline, parser)
        return compare(old, new)
    except (OSError, SyntaxError, ValueError) as e:
        print(f"import-fas: {e}", file=sys.stderr)
        return 2
