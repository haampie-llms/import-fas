# import-fas

Find the import statements that make a Python package's import graph cyclic.

Circular imports are hard to get rid of one at a time, because it is rarely obvious *which*
import to delete. `import-fas` builds the module import graph of a package and computes a
**minimum feedback arc set**: the smallest set of imports whose removal makes the graph
acyclic.

It is two independent halves — extracting the graph from a Python project with an AST walk,
and solving the feedback arc set exactly with [clingo](https://potassco.org/clingo/) — and
the graph in between is a plain file you can dump and read.

## Install

Not on PyPI yet:

```console
$ pip install git+https://github.com/haampie-llms/import-fas
```

## Use

```console
$ import-fas solve ~/spack/lib/spack/spack --exclude '^spack\.(vendor|test)\b' --inline
14 problematic import statements

All import cycles are broken by removing the following import statements:
---
spack/concretize imports: spack.bootstrap, spack.solver.asp
spack/install_test imports: spack.build_environment
spack/relocate imports: spack.bootstrap
spack/schema/repos imports: spack.repo
spack/spec imports: spack.patch, spack.provider_index, spack.repo, spack.store
spack/spec_parser imports: spack.spec
spack/traverse imports: spack.spec
spack/util/gpg imports: spack.bootstrap
spack/util/remote_file_cache imports: spack.util.web
spack/util/web imports: spack.util.parallel
---
```

```console
$ import-fas compare old/src/mypkg new/src/mypkg
The overall number of problematic import statements increased by 1 from 3 to 4. This is
likely a direct consequence of the following import statement:

mypkg/cli imports: mypkg.store
```

`compare` exits 1 when the new tree needs more removals than the old one, which is what you
want in CI:

```yaml
- uses: actions/checkout@v5
  with: { ref: "${{ github.event.pull_request.base.sha }}", path: old }
- uses: actions/checkout@v5
  with: { path: new }
- run: pip install git+https://github.com/haampie-llms/import-fas
- run: import-fas compare old/src/mypkg new/src/mypkg
```

## A worked example

At the very bottom of `src/werkzeug/http.py`, past the last function, sit two imports under a
comment that reads `# circular dependencies`. Deferring them to the end of the module is the
standard way out: by the time the cycle closes, everything the other side needs is defined.
`import-fas` knows nothing about that comment, and arrives at the same two imports:

```console
$ pip download --no-deps --no-binary :all: werkzeug==3.1.8 && tar xf werkzeug-3.1.8.tar.gz
$ import-fas solve werkzeug-3.1.8/src/werkzeug
2 problematic import statements

All import cycles are broken by removing the following import statements:
---
werkzeug/http imports: werkzeug.datastructures, werkzeug.sansio.http
---
```

The second of the two can be traced to one commit: a refactor that moved a handful of
functions out of `werkzeug.http` into a new `werkzeug.sansio.http`, which imports them back.
Nothing broke, because the same commit put the new import at the bottom of the file. That is
the point — a cycle is cheapest to reconsider while the change that adds it is still in
review, and a passing test suite is not evidence that none was added:

```console
$ git clone https://github.com/pallets/werkzeug
$ git -C werkzeug worktree add ../before b42d1a4b^
$ git -C werkzeug worktree add ../after b42d1a4b
$ import-fas compare before/src/werkzeug after/src/werkzeug
The overall number of problematic import statements increased by 1 from 1 to 2. This is
likely a direct consequence of the following import statement:

werkzeug/http imports: werkzeug.sansio.http

All import cycles are broken by removing the following import statements:
---
werkzeug/datastructures imports: werkzeug.http
werkzeug/http imports: werkzeug.sansio.http
---
```

Two is a deliberately small number, and it is worth knowing what it leaves out. The other
standard workaround is to move an import inside the function that needs it, which takes the
cycle out of import time without taking it out of the design. `--inline` counts those as
well, and the same package goes from 2 to 8.

Several projects already guard this in CI from the other side: aiohttp's
[`test_circular_imports.py`][aiohttp-test] and pytest's [`test_meta.py`][pytest-test] import
every submodule in a fresh interpreter and fail if one of them cannot stand on its own. That
catches a cycle at the moment it breaks. A feedback arc set is the same question asked one
step earlier: it counts the cycles that still work, and names the import that closed them.

[aiohttp-test]: https://github.com/aio-libs/aiohttp/blob/master/tests/test_circular_imports.py
[pytest-test]: https://github.com/pytest-dev/pytest/blob/main/testing/test_meta.py

## Dumping the graph

When the answer surprises you, the question is almost always about the graph rather than the
solver: an edge you did not expect, a module that is not there, an `--exclude` that matched
more than you meant. `import-fas graph` writes out exactly what the solver was given.

```console
$ import-fas graph ~/spack/lib/spack/spack --exclude '^spack\.(vendor|test)\b' -o graph.json
$ import-fas solve graph.json
14 problematic import statements
```

`solve` and `compare` take a dumped graph anywhere they take a package directory, so you can
look at the file, edit it, and re-solve without parsing the tree again — or hand it to a
different feedback-arc-set solver.

### The graph file

`-f json` (the default) is one object:

```json
{"nodes": ["pkg", "pkg.a", "pkg.b"], "edges": [[0, 1], [1, 2], [2, 1]]}
```

`-f text` is the same thing without a JSON parser: the number of nodes, the node names one
per line, the number of edges, then the edges as index pairs.

```
3
pkg
pkg.a
pkg.b
3
0 1
1 2
2 1
```

An edge `i j` means node `i` imports node `j`. Both formats list nodes sorted by name and
edges sorted by index, so a dump is reproducible, and nodes that neither import nor are
imported are still listed.

### In Python

```python
import import_fas

graph = import_fas.build_graph("lib/spack/spack", exclude=r"^spack\.(vendor|test)\b")
fas = import_fas.minimum_feedback_arc_set(graph)
print(graph.names(fas))  # [('spack.concretize', 'spack.solver.asp'), ...]
```

## What ends up in the graph

- Only the package's own modules. Imports of anything outside it are dropped, as are modules
  matching `--exclude`.
- `--exclude` is an `re.search` on the dotted module name, so anchor it if you mean to. A
  package that matches is pruned along with everything under it.
- `from foo import bar` is an edge to `foo.bar` if that is a submodule, and to `foo` if it is
  an attribute. `import a.b.c` records a single edge to `a.b.c`, even though importing it also
  runs `a/__init__.py` and `a/b/__init__.py`, so a cycle that closes only through one of those
  parent modules is not in the graph and will not be reported.
- The bodies of `if TYPE_CHECKING:` and `if __name__ == "__main__":` are skipped, since
  neither runs on import; the `else:` branch of either is not. Every other conditional import
  counts, including both arms of a `try: ... except ImportError:`.
- Imports inside functions and classes only count with `--inline`.
- A package inherits the imports of the submodules it re-exports, to a fixed point: if `x`
  imports `x.y` and `x.y` imports `foo`, then `x` imports `foo`. Deleting `x -> x.y` is not a
  real option when the point of `x` is to expose `x.y`.

Not every cycle in the report is a problem to solve. A submodule that does `import pkg as p`
purely to reach `p.thing` at call time is in a cycle with its own package, and the language
tolerates it; in packages written that way it can account for most of the count. Those are
real edges, so they stay in the graph. `--exclude` will not help here — excluding a package
prunes everything under it, and the root is the whole tree — but the dumped graph will:
dropping the edges that point at the root node and re-solving asks the narrower question.

A graph usually has many optimal solutions, so treat the *count* as the contract and the
particular set as one suggestion among several.
