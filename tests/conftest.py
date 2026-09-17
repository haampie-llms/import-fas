import pytest


@pytest.fixture
def tree(tmp_path):
    """Write a package from ``{"pkg/a.py": "import pkg.b"}`` and return its directory."""

    def make(files):
        root = None
        for name, source in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(source, bytes):
                path.write_bytes(source)
            else:
                path.write_text(source)
            if root is None:
                root = name.split("/")[0]
        return str(tmp_path / root)

    return make
