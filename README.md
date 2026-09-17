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
  runs `a/__init__.py` and `a/b/__init__.py`.
- The body of `if TYPE_CHECKING:` is skipped; its `else:` branch is not. Every other
  conditional import counts, including both arms of a `try: ... except ImportError:`.
- Imports inside functions and classes only count with `--inline`.
- A package inherits the imports of the submodules it re-exports, to a fixed point: if `x`
  imports `x.y` and `x.y` imports `foo`, then `x` imports `foo`. Deleting `x -> x.y` is not a
  real option when the point of `x` is to expose `x.y`.

A graph usually has many optimal solutions, so treat the *count* as the contract and the
particular set as one suggestion among several.
