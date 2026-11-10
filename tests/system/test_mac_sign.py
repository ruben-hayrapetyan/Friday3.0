"""Mac/sign.sh (C88) with the real codesign, signing ad hoc ("-") a small app built here: a program and a library
compiled into its Resources the way the bundled Python's are, beside files that only look compiled. Every compiled
file comes out signed under the hardened runtime, the program with the planner's entitlements, the app with the
calendars'; what isn't compiled is left alone; a certificate that isn't there is said and nothing passes."""

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("cc"), reason="codesign and cc")


def compile_(source: str, out: Path, *flags: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cc", "-x", "c", "-", "-o", str(out), *flags], input=source, text=True, check=True)


@pytest.fixture
def app(tmp_path: Path) -> Path:
    app = tmp_path / "Friday.app"
    contents = app / "Contents"
    compile_("int main(void) { return 0; }", contents / "MacOS" / "Friday")
    (contents / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Friday",
                                                          "CFBundleIdentifier": "test.friday.sign"}))  # fmt: skip
    python = contents / "Resources" / "friday" / "python"
    compile_("int main(void) { return 0; }", python / "bin" / "python3.12")
    compile_("int answer(void) { return 42; }", python / "lib" / "site-packages" / "m.so", "-shared")
    (python / "lib" / "java.class").write_bytes(b"\xca\xfe\xba\xbe\x00\x00\x00\x41" + bytes(64))  # not universal
    (python / "lib" / "module.py").write_text("x = 1\n")
    (python / "bin" / "python3").symlink_to("python3.12")
    return app


def sign(app: Path, identity: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(REPO / "Mac" / "sign.sh"), str(app), identity], capture_output=True, text=True,
                          timeout=120)  # fmt: skip


def entitlements(path: Path) -> dict:
    said = subprocess.run(["codesign", "-d", "--entitlements", "-", "--xml", str(path)], capture_output=True)
    return plistlib.loads(said.stdout) if said.stdout.strip() else {}


def flags(path: Path) -> str:
    said = subprocess.run(["codesign", "-dv", str(path)], capture_output=True, text=True).stderr
    return next((line for line in said.splitlines() if "flags=" in line), "")


def test_every_compiled_file_is_signed_under_the_hardened_runtime_with_its_entitlements(app: Path) -> None:
    done = sign(app, "-")
    assert done.returncode == 0, done.stderr
    assert "1 libraries, 1 programs" in done.stdout and "replacing existing" not in done.stdout + done.stderr
    python = app / "Contents" / "Resources" / "friday" / "python"
    for path in (app, python / "bin" / "python3.12", python / "lib" / "site-packages" / "m.so"):
        assert "runtime" in flags(path), path
    jit = entitlements(python / "bin" / "python3.12")
    assert jit["com.apple.security.cs.allow-jit"] and jit["com.apple.security.cs.allow-unsigned-executable-memory"]
    # ad hoc has no team, so only a try-out lets the program load its libraries; a Developer ID never needs it
    assert jit["com.apple.security.cs.disable-library-validation"]
    assert entitlements(app) == {"com.apple.security.personal-information.calendars": True}
    assert entitlements(python / "lib" / "site-packages" / "m.so") == {}
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)


def test_the_entitlements_a_download_gets_ask_for_no_more_than_the_planner_and_the_calendars_need() -> None:
    python = plistlib.loads((REPO / "Mac" / "entitlements" / "python.plist").read_bytes())
    assert python == {"com.apple.security.cs.allow-jit": True,
                      "com.apple.security.cs.allow-unsigned-executable-memory": True}  # fmt: skip
    app = plistlib.loads((REPO / "Mac" / "entitlements" / "app.plist").read_bytes())
    assert app == {"com.apple.security.personal-information.calendars": True}


def test_what_isnt_compiled_is_left_as_it_was(app: Path) -> None:
    lib = app / "Contents" / "Resources" / "friday" / "python" / "lib"
    before = {p: p.read_bytes() for p in (lib / "java.class", lib / "module.py")}
    assert sign(app, "-").returncode == 0
    assert all(p.read_bytes() == b for p, b in before.items())


def test_a_certificate_that_isnt_in_the_keychain_is_said_and_the_app_isnt_passed(app: Path) -> None:
    done = sign(app, "Developer ID Application: Nobody (NOTEAM0000)")
    assert done.returncode != 0 and "Not signed:" in done.stderr
    assert "Developer ID Application: Nobody" in done.stderr  # codesign's own words, not swallowed


def test_something_that_isnt_an_app_is_refused(tmp_path: Path) -> None:
    done = sign(tmp_path, "-")
    assert done.returncode != 0 and "no app at" in done.stderr
