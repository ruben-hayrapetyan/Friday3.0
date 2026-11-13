"""The download site (HOSTED.md H106, H116, H117, H129, H130; step 1). Glass box: build_pages.py wraps each page in
the header and footer, marking the page it is. Black box over HTTP, as served: every page answers, every link and
picture on them resolves on the site, every picture says what it shows, nothing is loaded from elsewhere (no
trackers, H106 privacy), and the download button points at a disk image that is there."""

import functools
import importlib.util
import json
import re
import shutil
import subprocess
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
        self.canonical: list[str] = []  # the page's own https address (H184): named, not loaded

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"] or "")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"] or "")
            if a.get("aria-current") == "page":
                self.current.append(a["href"] or "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical.append(a.get("href") or "")
        elif tag == "link" and a.get("href"):
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


def test_search_engines_name_the_site_friday_with_its_icon() -> None:
    """H181 (11 Nov: "the google search doesn't have a logo and i just want the name to be Friday"): the home page's
    title is Friday, its structured data names the site Friday with the icon as its logo, and the icons it links are
    at sizes Google shows (a multiple of 48 pixels square)."""
    home = (SITE / "index.html").read_text()
    assert "<title>Friday</title>" in home
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)[1])
    names = {node["@type"]: node for node in data["@graph"]}
    assert names["WebSite"]["name"] == "Friday" and names["Organization"]["logo"].endswith("/images/icon.png")
    for size in re.findall(r'rel="icon" type="image/png" sizes="(\d+)x\1"', home):
        assert int(size) % 48 == 0, size
        assert (SITE / "images" / f"icon-{size}.png").exists()


def test_slacks_return_page_forwards_only_to_this_mac() -> None:
    """H182: Slack's sign-in comes back to an https page that sends the browser on to Friday on the person's own Mac
    (127.0.0.1 at the port in `state`), never anywhere else, and isn't listed by search engines."""
    page, script = (SITE / "slack-signin.html").read_text(), (SITE / "slack-signin.js").read_text()
    assert '<script src="/slack-signin.js">' in page and 'name="robots" content="noindex"' in page
    assert re.findall(r"https?://[^\"' )]+", script) == ["http://127.0.0.1:"]
    assert "/^\\d{4,5}$/" in script and "location.replace" in script


@pytest.mark.parametrize("page", PAGES)
def test_every_page_names_its_https_address(site: str, page: str) -> None:
    """H184: Google had the home page at http://, which the site also answered; each page names its own https address
    (the home page as the site's root), and only that one."""
    want = "https://friday-scheduler.com/" + ("" if page == "index.html" else page)
    assert parsed(site, page).canonical == [want]


def test_the_home_page_offers_the_week_as_its_picture() -> None:
    """H184 (13 Nov: "have there be a nice picture - not nothingg"): the week is the picture offered beside the result
    (Open Graph, the page's structured data), at its true size, and large previews are allowed; the icon stays the
    logo (H181)."""
    home = (SITE / "index.html").read_text()
    meta = dict(re.findall(r'<meta (?:property|name)="([^"]+)" content="([^"]*)">', home))
    assert meta["og:image"] == "https://friday-scheduler.com/images/week.jpg"
    week = (SITE / "images" / "week.jpg").read_bytes()
    found = re.search(rb"\xff[\xc0\xc2]..\x08(..)(..)", week, re.S)  # a JPEG's frame header: height, then width
    assert found and (int(meta["og:image:width"]), int(meta["og:image:height"])) == (
        int.from_bytes(found[2], "big"),
        int.from_bytes(found[1], "big"),
    )
    assert "max-image-preview:large" in meta["robots"] and meta["twitter:card"] == "summary_large_image"
    assert len(meta["og:image:alt"]) > 20
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)[1])
    nodes = {node["@type"]: node for node in data["@graph"]}
    assert nodes["WebPage"]["primaryImageOfPage"] == meta["og:image"]
    assert nodes["Organization"]["logo"].endswith("/images/icon.png")


def test_google_calendar_and_gmail_are_not_called_coming() -> None:
    """H186: they're in the download (Google's calendars through the Mac's Internet Accounts, Gmail with an app
    password), so no page says they're coming, and the FAQ says how."""
    for page in PAGES:
        text = (SITE / page).read_text()
        assert "coming to the download" not in text and "once they're in the download" not in text, page
    home = (SITE / "index.html").read_text()
    answer = re.search(r"Does it work with Google Calendar\?</summary><p>(.*?)</p>", home)[1]
    assert answer.startswith("Yes.") and "Internet Accounts" in answer and "app password" in answer


def test_privacy_and_the_terms_say_what_the_update_check_sends_and_the_code_sends_that() -> None:
    """H187: both pages say the check sends the version you have (and the address any request shows, which Cloudflare
    sees too), and the updater's request carries exactly that version."""
    privacy = (SITE / "privacy.html").read_text()
    update = re.search(r"<b>Looking for updates\.</b>(.*?)</li>", privacy, re.S)[1]
    assert "which version of Friday you have" in update and "Cloudflare" in update
    assert "sends nothing about you or your data;" not in update
    terms = (ROOT / "TERMS.md").read_text()
    assert "which version of Friday you have" in terms and "Cloudflare" in terms
    spec = importlib.util.spec_from_file_location("updates", ROOT / "src" / "friday" / "sync" / "updates.py")
    assert spec and spec.loader
    updates = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updates)
    assert updates.asking("https://friday-scheduler.com/updates.json", "0.4.1").get_header("User-agent") == (
        "Friday/0.4.1 (Mac)"
    )


def test_whats_new_download_is_matched_to_the_computer_like_the_home_page() -> None:
    """H189: the current version's Download on What's new is a [data-download] with its note, and the page runs the
    same download.js as the home page; older versions have no download."""
    page = (SITE / "whats-new.html").read_text()
    assert page.count("data-download>Download</a>") == 1 and page.count("data-download-other hidden") == 1
    assert '<script src="/download.js"></script>' in page
    current = re.search(r'<div class="version" id="([^"]+)">', page)[1]  # newest first
    assert f'href="/get/Friday-{current}.dmg" download data-download>' in page


HARNESS = r"""
// download.js in a made-up browser: argv[2] is the visitor (JSON), the result the buttons and notes as left.
const visitor = JSON.parse(process.argv[2]);
function el(attrs, text) {
  return { attrs: Object.assign({}, attrs), textContent: text, hidden: "hidden" in attrs, innerHTML: "",
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }, setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; } };
}
const buttons = [el({ href: "/get/Friday-0.4.1.dmg", download: "" }, "Download for Mac"),
                 el({ href: "/get/Friday-0.4.1.dmg", download: "" }, "Download")];
const notes = [el({ hidden: "" }, "")], macOnly = [el({}, "")];
const all = { "[data-download]": buttons, "[data-download-other]": notes, "[data-mac-only]": macOnly };
global.document = { querySelector: (q) => (all[q] || [])[0] || null, querySelectorAll: (q) => all[q] || [] };
const nav = { platform: visitor.platform, userAgent: visitor.agent, maxTouchPoints: visitor.touch || 0 };
if (visitor.arch !== undefined) nav.userAgentData = { platform: visitor.uaPlatform || "macOS",
  getHighEntropyValues: async () => (visitor.arch === null ? {} : { architecture: visitor.arch }) };
Object.defineProperty(global, "navigator", { value: nav, configurable: true });
require(process.argv[3]);
setTimeout(() => console.log(JSON.stringify({
  buttons: buttons.map((b) => ({ text: b.textContent, href: b.getAttribute("href"),
    off: b.getAttribute("aria-disabled") })),
  note: notes[0].hidden ? null : notes[0].innerHTML, macOnlyHidden: macOnly[0].hidden })), 20);
"""

MAC_SAFARI = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15"
MAC_CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"


def visit(tmp_path: Path, **visitor: object) -> dict:
    if not shutil.which("node"):
        pytest.skip("node isn't installed")
    harness = tmp_path / "harness.cjs"
    harness.write_text(HARNESS)
    script = tmp_path / "download.cjs"
    script.write_text((SITE / "download.js").read_text())
    run = subprocess.run(
        ["node", str(harness), json.dumps(visitor), str(script)], capture_output=True, text=True, check=True
    )
    return json.loads(run.stdout)


@pytest.mark.parametrize("arch", ["arm", None])
def test_an_apple_silicon_mac_or_one_that_does_not_say_keeps_the_download(tmp_path: Path, arch: str | None) -> None:
    for seen in (
        visit(tmp_path, platform="MacIntel", agent=MAC_CHROME, arch=arch),
        visit(tmp_path, platform="MacIntel", agent=MAC_SAFARI),
    ):  # Safari: no userAgentData
        assert all(b["href"] == "/get/Friday-0.4.1.dmg" and b["off"] is None for b in seen["buttons"])
        assert seen["note"] is None and seen["macOnlyHidden"] is False


def test_an_intel_mac_that_says_so_is_told_friday_needs_apple_silicon(tmp_path: Path) -> None:
    """H188: Chrome and Edge tell the chip ("x86" on Intel): the buttons say Friday needs an Apple silicon Mac, the
    note says why and still offers the file, and the Mac-only parts (the Terminal line) stay."""
    seen = visit(tmp_path, platform="MacIntel", agent=MAC_CHROME, arch="x86")
    assert {b["text"] for b in seen["buttons"]} == {"Friday needs an Apple silicon Mac"}
    assert all(b["href"] is None and b["off"] == "true" for b in seen["buttons"])
    assert "Intel chip" in seen["note"] and "Apple silicon (M1 or later)" in seen["note"]
    assert 'href="/get/Friday-0.4.1.dmg" download>Download anyway</a>' in seen["note"]
    assert seen["macOnlyHidden"] is False


@pytest.mark.parametrize(
    ("platform", "agent", "touch", "label"),
    [
        ("iPhone", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", 5, "Friday is a Mac app"),
        ("MacIntel", MAC_SAFARI, 5, "Friday is a Mac app"),  # an iPad asks for the desktop site
        ("Win32", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0", 0, "Friday is for Mac for now"),
        ("Linux x86_64", "Mozilla/5.0 (X11; Linux x86_64) Firefox/131.0", 0, "Friday is for Mac for now"),
    ],
)
def test_other_computers_are_told_friday_is_for_mac(
    tmp_path: Path, platform: str, agent: str, touch: int, label: str
) -> None:
    seen = visit(tmp_path, platform=platform, agent=agent, touch=touch)
    assert {b["text"] for b in seen["buttons"]} == {label} and all(b["href"] is None for b in seen["buttons"])
    assert "Download for Mac anyway</a>" in seen["note"] and seen["macOnlyHidden"] is True
