"""The download site (HOSTED.md H106, H116, H117; step 1). Glass box: build_pages.py wraps each page in the header
and footer, marking the page it is. Black box over HTTP, as served: every page answers, every link and picture on
them resolves on the site, every picture says what it shows, nothing is loaded from elsewhere (no trackers, H106
privacy), and the download button points at a disk image that is there."""

import functools
import importlib.util
import threading
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = ["index.html", "features.html", "help.html", "privacy.html", "whats-new.html"]


class Parts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.scripts: list[str] = []
        self.ids: set[str] = set()
        self.current: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"] or "")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"] or "")
            if a.get("aria-current") == "page":
                self.current.append(a["href"] or "")
        if tag == "link" and a.get("href"):
            self.links.append(a["href"] or "")
        if tag == "img":
            self.images.append(a)
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"] or "")


@pytest.fixture(scope="module")
def site() -> str:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a: None  # type: ignore[method-assign]
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def fetch(site: str, path: str) -> tuple[int, bytes]:
    with urlopen(site + path) as answer:
        return answer.status, answer.read()


def parsed(site: str, page: str) -> Parts:
    parts = Parts()
    parts.feed(fetch(site, "/" + page)[1].decode())
    return parts


@pytest.mark.parametrize("page", PAGES)
def test_every_page_answers_with_a_title_and_description(site: str, page: str) -> None:
    status, body = fetch(site, "/" + page)
    text = body.decode()
    assert status == 200 and "<title>" in text and 'name="description"' in text


@pytest.mark.parametrize("page", PAGES)
def test_every_link_and_picture_on_a_page_is_on_the_site(site: str, page: str) -> None:
    parts = parsed(site, page)
    for ref in parts.links + parts.scripts + [str(i.get("src")) for i in parts.images]:
        where = urlsplit(ref)
        assert not where.scheme and not where.netloc, f"{page} loads {ref} from elsewhere"
        if where.path.startswith("/downloads/"):
            continue  # the disk image: its own test
        assert fetch(site, where.path or "/" + page)[0] == 200, f"{page}: {ref}"
        if where.fragment and (where.path in ("", "/" + page) or where.path == "/" and page == "index.html"):
            assert where.fragment in parts.ids, f"{page}: #{where.fragment}"


@pytest.mark.parametrize("page", PAGES)
def test_every_picture_says_what_it_shows(site: str, page: str) -> None:
    for image in parsed(site, page).images:
        assert len(image.get("alt") or "") > 20, image


def test_the_download_button_points_at_a_disk_image_that_is_there(site: str) -> None:
    parts = parsed(site, "index.html")
    images = [link for link in parts.links if link.startswith("/downloads/") and link.endswith(".dmg")]
    assert images, "no download link"
    if not (SITE / images[0].lstrip("/")).exists():
        pytest.skip("the disk image is kept on the laptop, not in git")
    status, body = fetch(site, images[0])
    assert status == 200 and len(body) > 100_000_000


def load_builder():  # noqa: ANN201
    spec = importlib.util.spec_from_file_location("build_pages", ROOT / "build_pages.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # writes the pages again: the same as what is in git
    return module


def test_the_wrapper_marks_the_page_it_is_and_keeps_the_body() -> None:
    page = load_builder().page("help.html", "Help · Friday", "How to", "<h1>Help</h1>")
    parts = Parts()
    parts.feed(page)
    assert parts.current == ["/help.html"]
    assert "<h1>Help</h1>" in page and "<title>Help · Friday</title>" in page and "/style.css" in parts.links


def test_the_pages_in_git_are_what_the_wrapper_writes() -> None:
    before = {p: (SITE / p).read_text() for p in PAGES if p != "index.html"}
    load_builder()
    assert {p: (SITE / p).read_text() for p in before} == before
