# import-fas

A Python tool to find the least number of `import` statements to break all circular imports.

![A five-module import graph with two cycles; one edge, shown dashed, breaks both](https://raw.githubusercontent.com/haampie-llms/import-fas/main/docs/feedback-arc-set.svg)

It gives you short and actionable feedback to structure your Python package better.

It works by computing the so-called [Feedback Arc Set][1] on the graph of Python modules (nodes) and import statements (edges).

## Usage

```
import-fas [--exclude REGEX] [--inline] [--baseline OLD] [--dump-graph FILE] PACKAGE
```

### Listing problematic import statements

Use `import-fas path/to/pkg` to list the minimal import statements to delete to make the package acyclic: 

```console
$ import-fas werkzeug-3.1.8/src/werkzeug
werkzeug-3.1.8/src/werkzeug/http.py:1442: imports werkzeug.datastructures
werkzeug-3.1.8/src/werkzeug/http.py:1443: imports werkzeug.sansio.http
2 dependencies to remove
```

### Finding regressions

Use `--baseline` to see whether a new commit or version regresses the number of dependencies to remove:

```console
$ import-fas Werkzeug-2.2.0/src/werkzeug --baseline Werkzeug-2.1.2/src/werkzeug
Werkzeug-2.2.0/src/werkzeug/http.py:1305: imports werkzeug.sansio.http
dependencies to remove increased from 1 to 2
```

This check is useful in CI:

```yaml
- uses: actions/checkout@v5
  with: { ref: "${{ github.event.pull_request.base.sha }}", path: old }
- uses: actions/checkout@v5
  with: { path: new }
- run: pip install git+https://github.com/haampie-llms/import-fas
- run: import-fas new/src/mypkg --baseline old/src/mypkg
```

## Install

```
pip install git+https://github.com/haampie-llms/import-fas
```

## Options

- `--exclude REGEX`: exclude certain modules, for example: `'^app\.(vendor|tests)\b'`.
- `--inline`: also count imports inside functions and classes.
- `--baseline OLD`: an older version of the package. Lists the import statements this version added to the problem, and exits 1 if more dependencies have to go than before.
- `--dump-graph FILE`: write the import graph to `FILE` (`-` for stdout) instead of solving it.
- `--format json|text`: format of the dumped graph. Defaults to `text` when `FILE` ends in `.txt`, otherwise `json`.

## Exit status

- `0`: the dependencies were listed, or no more of them have to go than in the baseline.
- `1`: more dependencies have to go than in the baseline.
- `2`: a file could not be read or parsed, or the arguments were invalid.

## Python API

```python
import import_fas

graph = import_fas.build_graph("src/app", exclude=r"^app\.tests\b")
fas = import_fas.minimum_feedback_arc_set(graph)
print(graph.names(fas))  # [('app.db', 'app.models')]
```

## The import graph

The import graph is constructed statically using AST parsing. Imports under `if TYPE_CHECKING` and `if __name__ == "__main__"` are dropped. Dynamic imports inside functions and classes only count with `--inline`.

## Notes

Imports of *submodules* are never reported to make things actionable. Consider a module `foo` that imports a submodule `foo.bar` to re-export some of its API: it's practically impossible to eliminate this import. Technically this means that we're computing a constrained version of the feedback arc set.

Also notice there are typically many optimal solutions, but only one (arbitrary) solution is printed. For example a trivial cycle `a -> b -> c -> a` can be made acyclic by removing any edge.

## See also

- pylint's [`cyclic-import`][2], [pycycle][3] and [import-linter][4] report every cycle they find, one chain of modules per cycle. In a package with many cycles that is a long list; `import-fas` reports the few imports that break all of them.
- The minimum is exact, computed with [clingo](https://potassco.org/clingo/).

[1]: https://en.wikipedia.org/wiki/Feedback_arc_set
[2]: https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/cyclic-import.html
[3]: https://github.com/bndr/pycycle
[4]: (https://github.com/seddonym/import-linter