"""The download site (HOSTED.md H106, H116, H117, H129, H130; step 1). Glass box: build_pages.py wraps each page in
the header and footer, marking the page it is. Black box over HTTP, as served: every page answers, every link and
picture on them resolves on the site, every picture says what it shows, nothing is loaded from elsewhere (no
trackers, H106 privacy), and the download button points at a disk image that is there."""

import functools
import importlib.util
import json
import re
import threading
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SUPPORT = "friday_support@friday-scheduler.com"  # the only address the site shows (HOSTED.md H164, H166)
PAGES = [
    "index.html",
    "features.html",
    "help.html",
    "privacy.html",
    "whats-new.html",
    "contact.html",
    "contact-sent.html",
    "contact-wait.html",
    "terms.html",
]


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
        if ref == f"mailto:{SUPPORT}":
            continue  # Friday's own address (H166): a link to write, nothing loaded
        where = urlsplit(ref)
        assert not where.scheme and not where.netloc, f"{page} loads {ref} from elsewhere"
        if where.path.startswith(("/downloads/", "/get/")):
            continue  # the disk image and its counting link: their own tests
        assert fetch(site, where.path or "/" + page)[0] == 200, f"{page}: {ref}"
        if where.fragment and (where.path in ("", "/" + page) or where.path == "/" and page == "index.html"):
            assert where.fragment in parts.ids, f"{page}: #{where.fragment}"


@pytest.mark.parametrize("page", PAGES)
def test_every_picture_says_what_it_shows_or_is_marked_decoration(site: str, page: str) -> None:
    for image in parsed(site, page).images:
        alt = image.get("alt")
        assert alt is not None, image  # alt="" is decoration (the live Friday's poster, labelled by its button)
        assert alt == "" or len(alt) > 20, image


def test_the_download_button_points_at_a_disk_image_that_is_there(site: str) -> None:
    parts = parsed(site, "index.html")
    links = [link for link in parts.links if link.startswith("/get/") and link.endswith(".dmg")]
    assert links, "no download link"
    image = "/downloads/" + links[0].removeprefix("/get/")  # where the site's counting link sends you
    if not (SITE / image.lstrip("/")).exists():
        pytest.skip("the disk image is kept on the laptop, not in git")
    status, body = fetch(site, image)
    assert status == 200 and len(body) > 100_000_000


def load_builder():  # noqa: ANN201
    spec = importlib.util.spec_from_file_location("build_pages", ROOT / "build_pages.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_wrapper_marks_the_page_it_is_and_keeps_the_body() -> None:
    page = load_builder().page("help.html", "Help · Friday", "How to", "<h1>Help</h1>")
    parts = Parts()
    parts.feed(page)
    assert parts.current == ["/help.html"]
    assert "<h1>Help</h1>" in page and "<title>Help · Friday</title>" in page and "/style.css" in parts.links


def test_the_pages_in_git_are_what_the_builder_writes_from_the_record() -> None:
    before = {p: (SITE / p).read_text() for p in PAGES}
    load_builder().build(ROOT)
    assert {p: (SITE / p).read_text() for p in PAGES} == before
    assert not any("{{" in text for text in before.values())  # every placeholder filled


def test_the_pages_name_the_current_version_from_the_record() -> None:
    record = json.loads((ROOT / "releases" / "released.json").read_text())
    version = record["current"]
    home = (SITE / "index.html").read_text()
    assert f"/get/Friday-{version}.dmg" in home and f"Version {version}" in home
    assert f"Friday {version}" in (SITE / "whats-new.html").read_text()


def test_the_home_page_carries_the_replanning_week_and_no_live_app(site: str) -> None:
    page = fetch(site, "/")[1].decode()
    for part in ('id="board"', 'class="quickadd"', 'role="status"', 'class="pause"', 'class="chapters"', "/week.js"):
        assert part in page, part
    script = fetch(site, "/week.js")[1].decode()
    assert "prefers-reduced-motion" in script and "Replanned" in script  # still for reduced motion; says it replanned
    assert "<iframe" not in page and ":10000" not in page  # the live app was taken out (H130)


def test_sections_hide_for_their_entrance_only_when_scripts_run(site: str) -> None:
    css = fetch(site, "/style.css")[1].decode()
    assert ".js .reveal {" in css and "\n.reveal {" not in css  # without scripts, nothing stays hidden
    assert 'classList.add("js")' in fetch(site, "/")[1].decode()


def test_the_fonts_are_served_from_the_site_with_their_licences(site: str) -> None:
    css = fetch(site, "/style.css")[1].decode()
    fonts = [part.split(")")[0].strip("\"'") for part in css.split("url(")[1:]]
    assert len(fonts) == 8
    for font in fonts:
        assert fetch(site, font)[0] == 200, font
    for name in ("archivo", "inter", "jetbrains-mono"):
        assert fetch(site, f"/fonts/LICENSE-{name}.txt")[1].startswith(b"Copyright"), name


def test_no_colour_gradients_in_the_look() -> None:
    css = (SITE / "style.css").read_text()
    assert "gradient(" not in css  # flat, as the app (preferences: no gradients)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_shows_fridays_own_address_and_no_other(site: str, page: str) -> None:
    text = fetch(site, "/" + page)[1].decode()
    assert f'href="mailto:{SUPPORT}"' in text
    assert set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text)) <= {SUPPORT}  # no personal address anywhere
