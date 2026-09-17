import pathlib

import pytest

from import_fas import build_graph


def edges(graph):
    return set(graph.names(graph.edges))


def test_from_import_submodule(tree):
    d = tree({"pkg/__init__.py": "", "pkg/y.py": "", "pkg/m.py": "from . import y"})
    assert edges(build_graph(d)) == {("pkg.m", "pkg.y")}


def test_from_import_attribute(tree):
    d = tree({"pkg/__init__.py": "thing = 1", "pkg/m.py": "from . import thing"})
    assert edges(build_graph(d)) == {("pkg.m", "pkg")}


def test_from_subpackage_import_submodule(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/y.py": "",
            "pkg/m.py": "from .sub import y",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.sub.y")}


def test_from_subpackage_import_attribute(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/m.py": "from .sub import thing",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.sub")}


def test_from_module_import_star(tree):
    d = tree({"pkg/__init__.py": "", "pkg/d.py": "", "pkg/m.py": "from pkg.d import *"})
    assert edges(build_graph(d)) == {("pkg.m", "pkg.d")}


def test_import_as_ignores_the_alias(tree):
    d = tree({"pkg/__init__.py": "", "pkg/e.py": "", "pkg/m.py": "import pkg.e as x"})
    assert edges(build_graph(d)) == {("pkg.m", "pkg.e")}


def test_dotted_import_records_one_edge(tree):
    """``import pkg.a.b`` runs pkg/a/__init__.py too, but only the leaf edge is recorded."""
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/a/__init__.py": "",
            "pkg/a/b.py": "",
            "pkg/m.py": "import pkg.a.b",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.a.b")}


def test_relative_import_from_the_parent_package(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/m.py": "from ..a import thing",
        }
    )
    assert edges(build_graph(d)) == {("pkg.sub.m", "pkg.a")}


def test_imports_outside_the_package_are_dropped(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/m.py": "import os\nimport other.thing\nfrom re import X",
        }
    )
    assert edges(build_graph(d)) == set()


@pytest.mark.parametrize("test", ["TYPE_CHECKING", "typing.TYPE_CHECKING"])
def test_type_checking_body_is_skipped_but_its_else_is_kept(tree, test):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/b.py": "",
            "pkg/c.py": "",
            "pkg/m.py": f"if {test}:\n    import pkg.b\nelse:\n    import pkg.c\n",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.c")}


def test_negated_type_checking_is_not_special(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/b.py": "",
            "pkg/m.py": "if not TYPE_CHECKING:\n    import pkg.b\n",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.b")}


def test_both_arms_of_a_try_except_import(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/b.py": "",
            "pkg/c.py": "",
            "pkg/m.py": "try:\n    import pkg.b\nexcept ImportError:\n    import pkg.c\n",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.b"), ("pkg.m", "pkg.c")}


@pytest.mark.parametrize("scope", ["def f():", "class C:"])
def test_inline_imports(tree, scope):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/b.py": "",
            "pkg/m.py": f"{scope}\n    import pkg.b\n",
        }
    )
    assert edges(build_graph(d)) == set()
    assert edges(build_graph(d, inline=True)) == {("pkg.m", "pkg.b")}


def test_re_exports_propagate_to_a_fixed_point(tree):
    """x re-exports x.y, which re-exports x.y.z, which imports foo: x pays for foo too."""
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/foo.py": "",
            "pkg/x/__init__.py": "from . import y",
            "pkg/x/y/__init__.py": "from . import z",
            "pkg/x/y/z.py": "import pkg.foo",
        }
    )
    assert ("pkg.x", "pkg.foo") in edges(build_graph(d))


def test_propagation_does_not_invent_a_self_import(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/x/__init__.py": "from . import y",
            "pkg/x/y.py": "import pkg.x",
        }
    )
    assert ("pkg.x", "pkg.x") not in edges(build_graph(d))


def test_an_attribute_import_of_the_own_package_is_not_an_edge(tree):
    """``from . import thing`` in pkg/__init__.py resolves to pkg, which is not a cycle."""
    d = tree({"pkg/__init__.py": "from . import thing"})
    assert edges(build_graph(d)) == set()


def test_exclude_drops_modules_and_prunes_subpackages(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/keep.py": "import pkg.vendor.inner",
            "pkg/vendor/__init__.py": "",
            "pkg/vendor/inner.py": "import pkg.keep",
        }
    )
    graph = build_graph(d, exclude=r"^pkg\.vendor\b")
    assert edges(graph) == set()
    assert graph.nodes == ["pkg", "pkg.keep"]


def test_modules_without_any_import_are_still_nodes(tree):
    d = tree({"pkg/__init__.py": "", "pkg/lonely.py": ""})
    graph = build_graph(d)
    assert graph.nodes == ["pkg", "pkg.lonely"]
    assert graph.edges == []


def test_a_syntax_error_names_the_file(tree):
    d = tree({"pkg/__init__.py": "", "pkg/bad.py": "def (\n"})
    with pytest.raises(SyntaxError) as excinfo:
        build_graph(d)
    assert excinfo.value.filename.endswith("bad.py")


def test_a_coding_cookie_is_honored(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/b.py": "",
            "pkg/m.py": b"# -*- coding: latin-1 -*-\nx = '\xe9'\nimport pkg.b\n",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.b")}


def test_the_graph_is_reproducible(tree):
    d = tree(
        {"pkg/__init__.py": "", "pkg/a.py": "import pkg.b", "pkg/b.py": "import pkg.a"}
    )
    assert build_graph(d) == build_graph(d)


def test_module_resolution_is_not_cached_across_calls(tree):
    d = tree({"pkg/__init__.py": "", "pkg/m.py": "from . import thing"})
    assert edges(build_graph(d)) == {("pkg.m", "pkg")}
    pathlib.Path(d, "thing.py").write_text("")
    assert edges(build_graph(d)) == {("pkg.m", "pkg.thing")}


def test_a_directory_without_an_init_is_not_a_package(tree):
    d = tree({"pkg/__init__.py": ""})
    with pytest.raises(ValueError, match="no __init__.py"):
        build_graph(str(pathlib.Path(d).parent))


def test_a_directory_whose_name_is_not_an_identifier(tmp_path):
    (tmp_path / "my-pkg").mkdir()
    (tmp_path / "my-pkg" / "__init__.py").write_text("")
    with pytest.raises(ValueError, match="not a valid package name"):
        build_graph(str(tmp_path / "my-pkg"))


def test_a_missing_directory(tmp_path):
    with pytest.raises(ValueError, match="not a package"):
        build_graph(str(tmp_path / "nope"))


@pytest.mark.parametrize("test", ['__name__ == "__main__"', '"__main__" == __name__'])
def test_main_block_is_skipped_but_its_else_is_kept(tree, test):
    """The demo block at the bottom of a module does not run when it is imported."""
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/b.py": "",
            "pkg/c.py": "",
            "pkg/m.py": f"if {test}:\n    import pkg.b\nelse:\n    import pkg.c\n",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.c")}


def test_other_name_comparisons_are_not_special(tree):
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/b.py": "",
            "pkg/c.py": "",
            "pkg/m.py": """if __name__ == "pkg.m":
    import pkg.b
if __name__ != "__main__":
    import pkg.c
""",
        }
    )
    assert edges(build_graph(d)) == {("pkg.m", "pkg.b"), ("pkg.m", "pkg.c")}
