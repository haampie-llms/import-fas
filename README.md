# import-fas

Find the import statements that make a Python package's import graph cyclic.

Circular imports are hard to get rid of one at a time, because it is rarely obvious *which*
import to delete. `import-fas` builds the module import graph of a package and computes a
**minimum feedback arc set**: the smallest set of imports whose removal makes the graph
acyclic.

It is two independent halves, and you can use either on its own:

1. **extract** a graph from a Python project — a pure standard-library AST walk;
2. **solve** the feedback arc set — exactly, with [clingo](https://potassco.org/clingo/).

The graph in between is a plain file of nodes and edges, so you can stop after step 1 and
bring your own solver.

## Install

```console
$ pip install import-fas
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
- run: pip install import-fas
- run: import-fas compare old/src/mypkg new/src/mypkg
```

## Use your own solver

Every positional argument is either a package directory or a graph file, so the two halves
split at any point:

```console
$ import-fas graph ~/spack/lib/spack/spack --exclude '^spack\.(vendor|test)\b' -o graph.json
$ my-solver graph.json > fas.txt     # Julia, networkx, an ILP, a heuristic, anything
$ import-fas solve graph.json --fas fas.txt
```

`solve --fas` never solves anything. It checks that removing those edges really does break
every cycle — a wrong or stale solution is an error, not a silent pass — and then prints the
usual report. `compare` takes `--fas-old` and `--fas-new` the same way.

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

Both list nodes sorted by name and edges sorted by index, so a dump is reproducible. An edge
`i j` means node `i` imports node `j`. Nodes that neither import nor are imported are still
listed, and `import-fas solve` reads either format back.

### The solution file

One edge per line as two node indices into the graph file it was computed from; `#` starts a
comment, blank lines are ignored.

```
# my-solver v1.2, objective 14
2 1
5 3
```

### In process

The solver protocol is `Callable[[Graph], list[Edge]]` — there is nothing to register.

```python
import import_fas

graph = import_fas.build_graph("lib/spack/spack", exclude=r"^spack\.(vendor|test)\b")
fas = my_heuristic(graph)  # list[tuple[int, int]]
assert import_fas.is_acyclic(graph, fas)
print(graph.names(fas))  # [('spack.concretize', 'spack.solver.asp'), ...]
```

## What ends up in the graph

- Only the package's own modules. Imports of anything outside it are dropped, as are modules
  matching `--exclude`.
- `--exclude` is an `re.search` on the dotted module name, so anchor it if you mean to. A
  package that matches is pruned along with everything under it.
- `from foo import bar` is an edge to `foo.bar` if that is a submodule, and to `foo` if it is
  an attribute. `import a.b.c` records a single edge to `a.b.c`, even though importing it also
  runs `a/__init__.py` and `a/b/__init__.py`.
- The body of `if TYPE_CHECKING:` is skipped; its `else:` branch is not. Every other
  conditional import counts, including both arms of a `try: ... except ImportError:`.
- Imports inside functions and classes only count with `--inline`.
- A package inherits the imports of the submodules it re-exports, to a fixed point: if `x`
  imports `x.y` and `x.y` imports `foo`, then `x` imports `foo`. Deleting `x -> x.y` is not a
  real option when the point of `x` is to expose `x.y`.

A graph usually has many optimal solutions, so treat the *count* as the contract and the
particular set as one suggestion among several.
