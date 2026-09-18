# import-fas

A Python tool to find the least number of `import` statements to remove so that your imports are acyclic.

![A five-module import graph with two cycles; one edge, shown dashed, breaks both](https://raw.githubusercontent.com/haampie-llms/import-fas/main/docs/feedback-arc-set.svg)

It gives you short and actionable feedback to structure your Python package better.

It works by computing the so-called [Feedback Arc Set][1] on the graph of Python modules (nodes) and import statements (edges).

## Usage

```
import-fas solve   [--exclude REGEX] [--inline] PACKAGE_DIR_OR_GRAPH
import-fas compare [--exclude REGEX] [--inline] OLD NEW
import-fas graph   [--exclude REGEX] [--inline] [-o FILE] [-f json|text] PACKAGE_DIR_OR_GRAPH
```

### Listing the problematic import

Use `import-fas solve path/to/pkg` to list the minimal import statements to delete to make the package acyclic: 

```console
$ import-fas solve werkzeug-3.1.8/src/werkzeug
2 problematic import statements

All import cycles are broken by removing the following import statements:
---
werkzeug/http imports: werkzeug.datastructures, werkzeug.sansio.http
---
```

### Finding regressions

Use `import-fas compare` to see whether a new commit or version regresses the number of problematic import statements:

```console
$ import-fas compare Werkzeug-2.1.2/src/werkzeug Werkzeug-2.2.0/src/werkzeug
The overall number of problematic import statements increased by 1 from 1 to 2. This is
likely a direct consequence of the following import statement:

werkzeug/http imports: werkzeug.sansio.http
```

This command is useful in CI:

```yaml
- uses: actions/checkout@v5
  with: { ref: "${{ github.event.pull_request.base.sha }}", path: old }
- uses: actions/checkout@v5
  with: { path: new }
- run: pip install git+https://github.com/haampie-llms/import-fas
- run: import-fas compare old/src/mypkg new/src/mypkg
```

## Install

```
pip install git+https://github.com/haampie-llms/import-fas
```

## Options

- `--exclude REGEX`: exclude certain modules, for example: `'^app\.(vendor|tests)\b'`.
- `--inline`: also count imports inside functions and classes.
- `-o FILE`: output file for `graph`. `-` is stdout and the default.
- `-f json|text`: output format for `graph`. Defaults to `text` when `-o` ends in `.txt`, otherwise `json`. `solve` and `compare` accept a dumped graph in place of a package directory.

## Exit status

- `0`: `solve` or `graph` ran, or `compare` found no increase.
- `1`: `compare` found an increase.
- `2`: a file could not be read or parsed, or the arguments were invalid.

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

- pylint's [`cyclic-import`](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/cyclic-import.html),
  [pycycle](https://github.com/bndr/pycycle) and [import-linter](https://github.com/seddonym/import-linter)
  report every cycle they find, one chain of modules per cycle. In a package with many
  cycles that is a long list; `import-fas` reports the few imports that break all of them.
- The minimum is exact, computed with [clingo](https://potassco.org/clingo/).

[1]: https://en.wikipedia.org/wiki/Feedback_arc_set
