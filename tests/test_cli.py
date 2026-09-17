import importlib.util
import json
import subprocess
import sys

import pytest

from import_fas import cli

needs_clingo = pytest.mark.skipif(
    importlib.util.find_spec("clingo") is None, reason="needs clingo"
)

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


@pytest.fixture
def no_clingo(monkeypatch):
    monkeypatch.setitem(sys.modules, "clingo", None)
    monkeypatch.delitem(sys.modules, "import_fas.fas", raising=False)


def test_graph_to_stdout(tree, run, capsys):
    assert run("graph", tree(CYCLE)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["nodes"] == ["pkg", "pkg.a", "pkg.b", "pkg.lonely"]
    assert data["edges"] == [[1, 2], [2, 1]]


def test_graph_needs_no_solver(tree, run, no_clingo, capsys):
    assert run("graph", tree(CYCLE)) == 0
    assert "import_fas.fas" not in sys.modules


@pytest.mark.parametrize("name,first", [("g.json", "{"), ("g.txt", "4")])
def test_the_format_follows_the_output_name(tree, run, tmp_path, name, first):
    out = tmp_path / name
    assert run("graph", tree(CYCLE), "-o", str(out)) == 0
    assert out.read_text().startswith(first)


@needs_clingo
def test_a_dumped_graph_can_be_read_back(tree, run, tmp_path, capsys):
    out = tmp_path / "g.txt"
    assert run("graph", tree(CYCLE), "-o", str(out)) == 0
    capsys.readouterr()
    assert run("solve", str(out)) == 0
    assert capsys.readouterr().out.startswith("1 problematic import statement\n")


def test_extraction_flags_do_not_apply_to_a_graph_file(tree, run, tmp_path):
    out = tmp_path / "g.json"
    run("graph", tree(CYCLE), "-o", str(out))
    with pytest.raises(SystemExit) as excinfo:
        run("solve", str(out), "--inline")
    assert excinfo.value.code == 2


@needs_clingo
def test_solve(tree, run, capsys):
    assert run("solve", tree(CYCLE)) == 0
    out = capsys.readouterr().out
    assert out.startswith("1 problematic import statement\n")
    assert "imports: pkg." in out


def test_solve_without_clingo(tree, run, no_clingo, capsys):
    with pytest.raises(SystemExit) as excinfo:
        run("solve", tree(CYCLE))
    assert excinfo.value.code == 2
    assert "clingo is not installed" in capsys.readouterr().err


def test_solve_with_a_solution_from_elsewhere(tree, run, no_clingo, tmp_path, capsys):
    d = tree(CYCLE)
    graph = tmp_path / "g.json"
    run("graph", d, "-o", str(graph))
    solution = tmp_path / "fas.txt"
    solution.write_text("# found by hand\n1 2\n")
    capsys.readouterr()
    assert run("solve", str(graph), "--fas", str(solution)) == 0
    assert capsys.readouterr().out.startswith("1 problematic import statement\n")


def test_a_solution_that_does_not_break_every_cycle(tree, run, tmp_path, capsys):
    d = tree(CYCLE)
    graph = tmp_path / "g.json"
    run("graph", d, "-o", str(graph))
    solution = tmp_path / "fas.txt"
    solution.write_text("")
    capsys.readouterr()
    assert run("solve", str(graph), "--fas", str(solution)) == 1
    assert "not a feedback arc set" in capsys.readouterr().err


def test_a_malformed_solution(tree, run, tmp_path, capsys):
    d = tree(CYCLE)
    graph = tmp_path / "g.json"
    run("graph", d, "-o", str(graph))
    solution = tmp_path / "fas.txt"
    solution.write_text("nonsense\n")
    capsys.readouterr()
    assert run("solve", str(graph), "--fas", str(solution)) == 2
    assert "expected two node indices" in capsys.readouterr().err


def test_a_syntax_error_in_the_package(tree, run, capsys):
    assert run("solve", tree({"pkg/__init__.py": "", "pkg/bad.py": "def (\n"})) == 2
    assert "bad.py" in capsys.readouterr().err


@needs_clingo
def test_compare_unchanged(tree, run, capsys):
    d = tree(CYCLE)
    assert run("compare", d, d) == 0
    assert "stayed the same: 1" in capsys.readouterr().out


@needs_clingo
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
    assert "decreased by 1 from 1 to 0" in capsys.readouterr().out


@needs_clingo
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
    out = capsys.readouterr().out
    assert "increased by 1 from 0 to 1" in out
    assert "This is likely a direct consequence" in out


@needs_clingo
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
    assert "stayed the same: 1" in capsys.readouterr().out


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


def test_importing_the_package_does_not_need_clingo():
    code = (
        "import sys; sys.modules['clingo'] = None; import import_fas; "
        "assert 'import_fas.fas' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
