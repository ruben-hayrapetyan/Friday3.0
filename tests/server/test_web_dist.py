"""Where the server finds the web app (29 Oct: "“Friday Test.app” would like to access files in your Downloads
folder... they keep coming"): the copy installed beside its Python before the repo's, so an installed Friday reads
nothing in ~/Downloads."""

from pathlib import Path

import pytest

from friday.server.main import web_dist


@pytest.fixture
def source(tmp_path: Path) -> Path:
    main = tmp_path / "repo" / "src" / "friday" / "server" / "main.py"
    main.parent.mkdir(parents=True)
    return main


def test_installed_beside_python_first(tmp_path: Path, source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRIDAY_WEB_DIST", raising=False)
    installed = tmp_path / "prefix" / "share" / "friday" / "web"
    installed.mkdir(parents=True)
    (installed / "index.html").write_text("<html>")
    assert web_dist(tmp_path / "prefix", source) == installed


def test_else_the_repo_while_working_on_it(tmp_path: Path, source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRIDAY_WEB_DIST", raising=False)
    assert web_dist(tmp_path / "prefix", source) == tmp_path / "repo" / "web" / "dist"


def test_a_chosen_one_wins(tmp_path: Path, source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_WEB_DIST", str(tmp_path / "mine"))
    assert web_dist(tmp_path / "prefix", source) == tmp_path / "mine"
