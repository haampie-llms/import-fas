# import-fas

Find the import statements that make a Python package's import graph cyclic.

![A five-module import graph with two cycles; one edge, shown dashed, breaks both](https://raw.githubusercontent.com/haampie-llms/import-fas/main/docs/feedback-arc-set.svg)

`app.db` imports `app.models` so that every table is registered before `create_all`.
That one import closes both cycles in the graph, so it is the minimum feedback arc set:
the smallest set of imports whose removal leaves no cycle.

## Usage

```
import-fas solve   [--exclude REGEX] [--inline] PACKAGE_DIR_OR_GRAPH
import-fas compare [--exclude REGEX] [--inline] OLD NEW
import-fas graph   [--exclude REGEX] [--inline] [-o FILE] [-f json|text] PACKAGE_DIR_OR_GRAPH
```

`solve` builds the import graph of a package from its AST, computes an exact minimum
feedback arc set with [clingo](https://potassco.org/clingo/), and prints the imports to
remove. `compare` solves two versions of a package and exits 1 when the new one needs
more removals. `graph` dumps the graph the solver sees; `solve` and `compare` accept
such a dump in place of a package directory.

## Install

```
pip install git+https://github.com/haampie-llms/import-fas
```

Requires Python 3.9 or later. Modules are parsed with the running interpreter's `ast`, so
use a Python at least as new as the syntax of the package under analysis.

## Options

- `--exclude REGEX`: drop modules whose dotted name matches, by `re.search`. A matching
  package is pruned with everything under it. Anchor prefixes: `'^app\.(vendor|tests)\b'`.
- `--inline`: also count imports inside functions and classes.
- `-o FILE`: output file for `graph`. `-` is stdout and the default.
- `-f json|text`: output format for `graph`. Defaults to `text` when `-o` ends in
  `.txt`, otherwise `json`.

## Examples

```console
$ pip download --no-deps --no-binary :all: werkzeug==3.1.8 && tar xf werkzeug-3.1.8.tar.gz
$ import-fas solve werkzeug-3.1.8/src/werkzeug
2 problematic import statements

All import cycles are broken by removing the following import statements:
---
werkzeug/http imports: werkzeug.datastructures, werkzeug.sansio.http
---
```

```console
$ import-fas compare before/src/werkzeug after/src/werkzeug
The overall number of problematic import statements increased by 1 from 1 to 2. This is
likely a direct consequence of the following import statement:

werkzeug/http imports: werkzeug.sansio.http
```

The same check on every pull request:

```yaml
- uses: actions/checkout@v5
  with: { ref: "${{ github.event.pull_request.base.sha }}", path: old }
- uses: actions/checkout@v5
  with: { path: new }
- run: pip install git+https://github.com/haampie-llms/import-fas
- run: import-fas compare old/src/mypkg new/src/mypkg
```

## Exit status

- `0`: `solve` or `graph` ran, or `compare` found no increase.
- `1`: `compare` found an increase.
- `2`: a file could not be read or parsed, or the arguments were invalid.

## Graph file

```json
{"nodes": ["pkg", "pkg.a", "pkg.b"], "edges": [[0, 1], [1, 2], [2, 1]]}
```

An edge `[i, j]` means node `i` imports node `j`. The `text` format is the node count, one
name per line, the edge count, then one `i j` pair per line. Nodes are sorted by name and
edges by index, so a dump is reproducible.

## Python API

```python
import import_fas

graph = import_fas.build_graph("src/app", exclude=r"^app\.tests\b")
fas = import_fas.minimum_feedback_arc_set(graph)
print(graph.names(fas))  # [('app.db', 'app.models')]
```

## What ends up in the graph

- Only the package's own modules. Imports of anything outside it are dropped.
- `from foo import bar` is an edge to `foo.bar` if that is a submodule, otherwise to `foo`.
- `import a.b.c` is one edge to `a.b.c`. A cycle that closes only through `a/__init__.py`
  or `a/b/__init__.py` is not in the graph.
- The bodies of `if TYPE_CHECKING:` and `if __name__ == "__main__":` are skipped. Every
  other conditional import counts, including both arms of `try: ... except ImportError:`.
- Imports inside functions and classes only count with `--inline`.
- A package inherits the imports of the submodules it re-exports, to a fixed point.
- A submodule that does `import pkg as p` to reach `p.thing` at call time is in a cycle
  with its own package. Such edges are real and stay; in packages written that way they
  can dominate the count. Drop the edges into the root from a dump and re-solve to ask
  the narrower question.
- A graph usually has many optimal solutions. The count is the contract; the set is one
  suggestion among several.

## See also

- [clingo](https://potassco.org/clingo/), the answer set solver behind the exact solution.
- aiohttp's [`test_circular_imports.py`](https://github.com/aio-libs/aiohttp/blob/master/tests/test_circular_imports.py)
  and pytest's [`test_meta.py`](https://github.com/pytest-dev/pytest/blob/main/testing/test_meta.py)
  import every submodule in a fresh interpreter and fail when one cannot stand on its own.
  They catch a cycle when it breaks; `compare` reports it when it is added.
