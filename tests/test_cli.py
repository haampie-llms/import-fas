import json
import re
import sys

import pytest

from import_fas import cli

CYCLE = {
    "pkg/__init__.py": "",
    "pkg/a.py": "import pkg.b",
    "pkg/b.py": "import pkg.a",
    "pkg/lonely.py": "",
}


@pytest.fixture
def run(monkeypatch):
    def go(*argv):
        monkeypatch.setattr(sys, "argv", ["import-fas", *argv])
        return cli.main()

    return go


def test_graph_to_stdout(tree, run, capsys):
    assert run("graph", tree(CYCLE)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["nodes"] == ["pkg", "pkg.a", "pkg.b", "pkg.lonely"]
    assert data["edges"] == [[1, 2], [2, 1]]


@pytest.mark.parametrize("name,first", [("g.json", "{"), ("g.txt", "4")])
def test_the_format_follows_the_output_name(tree, run, tmp_path, name, first):
    out = tmp_path / name
    assert run("graph", tree(CYCLE), "-o", str(out)) == 0
    assert out.read_text().startswith(first)


def test_a_dumped_graph_can_be_read_back(tree, run, tmp_path, capsys):
    out = tmp_path / "g.txt"
    assert run("graph", tree(CYCLE), "-o", str(out)) == 0
    capsys.readouterr()
    assert run("solve", str(out)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert re.fullmatch(r"pkg\.[ab]: imports pkg\.[ab]", lines[0])
    assert lines[-1] == "1 import to remove"


def test_extraction_flags_do_not_apply_to_a_graph_file(tree, run, tmp_path):
    out = tmp_path / "g.json"
    run("graph", tree(CYCLE), "-o", str(out))
    with pytest.raises(SystemExit) as excinfo:
        run("solve", str(out), "--inline")
    assert excinfo.value.code == 2


def test_solve(tree, run, capsys):
    assert run("solve", tree(CYCLE)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert re.search(r"pkg/[ab]\.py:1: imports pkg\.[ab]$", lines[0])
    assert lines[-1] == "1 import to remove"


def test_every_statement_behind_an_edge_is_listed(tree, run, capsys):
    """a -> b is on both cycles, so it is the unique answer, and it has two statements."""
    d = tree(
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "import pkg.b\nfrom pkg import b\n",
            "pkg/b.py": "import pkg.a\nimport pkg.c\n",
            "pkg/c.py": "import pkg.a",
        }
    )
    assert run("solve", d) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("pkg/a.py:1: imports pkg.b")
    assert lines[1].endswith("pkg/a.py:2: imports pkg.b")
    assert lines[2] == "1 import to remove"


def test_no_cycles(tree, run, capsys):
    assert run("solve", tree({"pkg/__init__.py": "", "pkg/a.py": "import pkg"})) == 0
    assert capsys.readouterr().out == "0 imports to remove\n"


def test_a_syntax_error_in_the_package(tree, run, capsys):
    assert run("solve", tree({"pkg/__init__.py": "", "pkg/bad.py": "def (\n"})) == 2
    assert "bad.py" in capsys.readouterr().err


def test_compare_unchanged(tree, run, capsys):
    d = tree(CYCLE)
    assert run("compare", d, d) == 0
    assert (
        capsys.readouterr().out.splitlines()[-1] == "imports to remove unchanged at 1"
    )


def test_compare_improved(tmp_path, run, capsys):
    for name, source in {
        "old/pkg/__init__.py": "",
        "old/pkg/a.py": "import pkg.b",
        "old/pkg/b.py": "import pkg.a",
        "new/pkg/__init__.py": "",
        "new/pkg/a.py": "import pkg.b",
        "new/pkg/b.py": "",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    assert (
        run("compare", str(tmp_path / "old" / "pkg"), str(tmp_path / "new" / "pkg"))
        == 0
    )
    assert capsys.readouterr().out == "imports to remove decreased from 1 to 0\n"


def test_compare_worse(tmp_path, run, capsys):
    for name, source in {
        "old/pkg/__init__.py": "",
        "old/pkg/a.py": "",
        "old/pkg/b.py": "",
        "new/pkg/__init__.py": "",
        "new/pkg/a.py": "import pkg.b",
        "new/pkg/b.py": "import pkg.a",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    assert (
        run("compare", str(tmp_path / "old" / "pkg"), str(tmp_path / "new" / "pkg"))
        == 1
    )
    lines = capsys.readouterr().out.splitlines()
    assert re.search(r"new/pkg/[ab]\.py:1: imports pkg\.[ab]$", lines[0])
    assert lines[-1] == "imports to remove increased from 0 to 1"


def test_compare_when_a_blamed_edge_is_gone(tmp_path, run, capsys):
    """The old solution names pkg.a -> pkg.b, which the new tree does not have at all."""
    for name, source in {
        "old/pkg/__init__.py": "",
        "old/pkg/a.py": "import pkg.b",
        "old/pkg/b.py": "import pkg.a",
        "old/pkg/c.py": "",
        "new/pkg/__init__.py": "",
        "new/pkg/a.py": "",
        "new/pkg/b.py": "import pkg.c",
        "new/pkg/c.py": "import pkg.b",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    assert (
        run("compare", str(tmp_path / "old" / "pkg"), str(tmp_path / "new" / "pkg"))
        == 0
    )
    assert (
        capsys.readouterr().out.splitlines()[-1] == "imports to remove unchanged at 1"
    )


@pytest.mark.parametrize(
    "env,colored",
    [
        ({}, False),
        ({"GITHUB_ACTIONS": "1"}, True),
        ({"GITHUB_ACTIONS": "1", "NO_COLOR": "1"}, False),
    ],
)
def test_color(monkeypatch, env, colored):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert ("\033[" in cli.colorize("hi", "1")) is colored
