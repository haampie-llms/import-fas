"""Build the import graph of a Python package."""

from __future__ import annotations

import ast
import dataclasses
import os
import re
from collections.abc import Callable, Iterable
from importlib.util import resolve_name

#: an edge as a pair of indices into :attr:`Graph.nodes`
Edge = tuple[int, int]
#: where an import statement is: absolute file path and 1-based line number
Location = tuple[str, int]


@dataclasses.dataclass
class Graph:
    """A module import graph: sorted module names, edges as index pairs into them, and per
    edge the import statements behind it, which a graph read from a file does not have."""

    nodes: list[str]
    edges: list[Edge]
    locations: dict[Edge, list[Location]] = dataclasses.field(
        default_factory=dict, compare=False
    )

    def names(self, edges: Iterable[Edge]) -> list[tuple[str, str]]:
        """The given edges as pairs of module names."""
        return [(self.nodes[i], self.nodes[j]) for i, j in edges]

    def indices(self, named: Iterable[tuple[str, str]]) -> list[Edge]:
        """Edges by name in this graph's index space; edges it does not have are dropped."""
        index = {name: i for i, name in enumerate(self.nodes)}
        edges = set(self.edges)
        pairs = ((index[a], index[b]) for a, b in named if a in index and b in index)
        return sorted(edge for edge in pairs if edge in edges)


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _is_main(test: ast.expr) -> bool:
    """``__name__ == "__main__"``, in either order."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    sides = (test.left, test.comparators[0])
    name = any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)
    main = any(isinstance(s, ast.Constant) and s.value == "__main__" for s in sides)
    return name and main


def _runs_on_import(test: ast.expr) -> bool:
    """Whether the body of ``if test:`` can run while the module is being imported."""
    return not _is_type_checking(test) and not _is_main(test)


class ImportVisitor(ast.NodeVisitor):
    def __init__(
        self, resolve: Callable[[str, str], str], current_pkg: str, inline: bool
    ):
        self.imported: dict[str, set[int]] = {}
        self.resolve = resolve
        self.current_pkg = current_pkg
        self.inline = inline

    def visit_Import(self, node: ast.Import) -> None:
        # import statements are always absolute
        for alias in node.names:
            self.imported.setdefault(alias.name, set()).add(node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # import from can be relative or absolute, and the alias can be a submodule or attribute
        module = resolve_name("." * node.level + (node.module or ""), self.current_pkg)
        for alias in node.names:
            name = self.resolve(module, alias.name)
            self.imported.setdefault(name, set()).add(node.lineno)

    def visit_If(self, node: ast.If) -> None:
        # the body of if TYPE_CHECKING and of if __name__ == "__main__" does not run on
        # import, but the else branch of either does
        if not _runs_on_import(node.test):
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_scope(self, node: ast.AST) -> None:
        if self.inline:
            self.generic_visit(node)

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = visit_scope


def _is_package_dir(entry: os.DirEntry[str]) -> bool:
    return (
        entry.name.isidentifier()
        and entry.is_dir(follow_symlinks=False)
        and os.path.isfile(os.path.join(entry.path, "__init__.py"))
    )


def _is_module_file(entry: os.DirEntry[str]) -> bool:
    return entry.is_file(follow_symlinks=False) and entry.name.endswith(".py")


def build_graph(
    package_dir: str, exclude: str | None = None, inline: bool = False
) -> Graph:
    """The import graph of a package. Modules whose name matches the ``exclude`` regex are left
    out; ``inline`` includes imports inside functions and classes."""
    package_dir = os.path.abspath(package_dir)
    root, pkg = os.path.split(package_dir)
    if not pkg.isidentifier():
        raise ValueError(f"{package_dir}: {pkg!r} is not a valid package name")
    if not os.path.isfile(os.path.join(package_dir, "__init__.py")):
        raise ValueError(f"{package_dir}: not a package, it has no __init__.py")

    cache: dict[tuple[str, str], str] = {}

    def resolve(module: str, attr: str) -> str:
        """``from foo import bar`` is ``foo.bar`` when bar is a submodule, else ``foo``."""
        key = (module, attr)
        if key not in cache:
            path = os.path.join(root, module.replace(".", os.sep), attr)
            is_module = os.path.isfile(f"{path}.py") or os.path.isfile(
                os.path.join(path, "__init__.py")
            )
            cache[key] = f"{module}.{attr}" if is_module else module
        return cache[key]

    inside = re.compile(rf"{re.escape(pkg)}(\.|$)").match
    excluded = re.compile(exclude).search if exclude else lambda _: False

    def keep(module: str) -> bool:
        """The graph holds this package's own modules, minus the excluded ones."""
        return bool(inside(module)) and not excluded(module)

    stack = [package_dir]
    modules: set[str] = set()
    edges: dict[tuple[str, str], list[Location]] = {}

    while stack:
        sub_pkg_dir = stack.pop()
        subpkg = os.path.relpath(sub_pkg_dir, root).replace(os.sep, ".")

        if not keep(subpkg):
            continue

        with os.scandir(sub_pkg_dir) as it:
            for entry in it:
                if _is_package_dir(entry):
                    stack.append(entry.path)
                elif _is_module_file(entry):
                    if entry.name == "__init__.py":
                        current = subpkg
                    else:
                        current = f"{subpkg}.{entry.name[:-3]}"
                    if not keep(current):
                        continue
                    modules.add(current)
                    visitor = ImportVisitor(resolve, subpkg, inline)
                    # bytes, so that ast honors a PEP 263 coding cookie
                    with open(entry.path, "rb") as f:
                        visitor.visit(ast.parse(f.read(), filename=entry.path))
                    for m, lines in visitor.imported.items():
                        # a self-loop is a cycle no reshuffling of imports can break
                        if m != current and keep(m):
                            edges.setdefault((current, m), []).extend(
                                (entry.path, line) for line in sorted(lines)
                            )

    nodes = sorted(modules | {dst for _, dst in edges})
    index = {node: i for i, node in enumerate(nodes)}
    locations = {(index[src], index[dst]): where for (src, dst), where in edges.items()}
    return Graph(nodes, sorted(locations), locations)
