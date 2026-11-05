"""Signing in and out of a hosted Friday (HOSTED.md S4, H81–H87): every page and API call needs a session (H83),
except these pages. The email link (H22) signs this browser in until you sign out (H25); asked from the Mac app
(H43), the browser instead hands the app a one-time code, which the app's window trades for a session of its own.

Cookies are secure, HTTP-only and same-site (H64); a sign-in or sign-out from another site's page is refused, as
`own_pages_only` refuses its changes. Signing out ends the session and clears what the browser kept of Friday.
"""

import html
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from friday.server import outgoing
from friday.server.accounts import Accounts

COOKIE = "friday_session"
FOREVER = 10 * 365 * 24 * 3600  # "until you sign out" (H25)
OPEN = ("/signin", "/auth/link", "/auth/app", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png")
APPS = {"friday-test": "Friday Test", "friday": "Friday"}  # the Mac apps that may ask, by their link scheme


def install(app: FastAPI, accounts: Accounts, clock: Callable[[], int], foreign: Callable[..., bool]) -> None:
    """The sign-in pages and the guard in front of everything else."""

    def public(request: Request) -> str:
        return os.environ.get("FRIDAY_PUBLIC_URL", str(request.base_url)).rstrip("/")

    def secure(request: Request) -> bool:
        return public(request).startswith("https://")

    def from_elsewhere(request: Request) -> bool:
        return foreign(request.headers.get("origin"), request.headers.get("host"))

    @app.middleware("http")
    async def signed_in_only(request: Request, call_next: Any) -> Any:
        path = request.url.path
        if path in OPEN or accounts.session(request.cookies.get(COOKIE), clock()) is not None:
            return await call_next(request)
        if path.startswith(("/api/", "/events", "/mcp", "/auth/")):
            return JSONResponse({"field": "session", "message": "Sign in first", "signin": "/signin"}, status_code=401)
        return RedirectResponse("/signin", status_code=303)

    @app.get("/signin", include_in_schema=False)
    def signin_page(request: Request, app: str = "") -> Response:
        if not app and accounts.session(request.cookies.get(COOKIE), clock()):
            return RedirectResponse("/", status_code=303)
        return page(form(app if app in APPS else ""))

    @app.post("/signin", include_in_schema=False)
    def send_link(request: Request, email: str = Form(""), app: str = Form("")) -> Response:
        if from_elsewhere(request):
            return page("<p>Friday takes sign-ins only from its own page.</p>", status=403)
        app = app if app in APPS else ""
        made = accounts.email_link(email, clock(), app or None)
        if made is not None:
            found, token = made
            try:
                outgoing.send(outgoing.signin_message(found.email, f"{public(request)}/auth/link?t={token}"))
            except outgoing.MailError as error:
                return page(form(app, email, str(error)), status=503)
        # The same answer whether or not the address has an account, so the page tells nobody who does.
        return page(
            f"<h2>Check your email</h2><p>If <b>{html.escape(email.strip())}</b> has a Friday account, a link to sign "
            "in is on its way. It works once, for 15 minutes.</p>"
            f'<p class="quiet"><a href="/signin{"?app=" + app if app else ""}">Use another address</a></p>'
        )

    @app.get("/auth/link", include_in_schema=False)
    def open_link(request: Request, t: str = "") -> Response:
        redeemed = accounts.redeem(t, "email", clock())
        if redeemed is None:
            return page(
                "<h2>That link has been used or is too old</h2><p>Each link works once, for 15 minutes.</p>"
                '<p><a class="button" href="/signin">Send a new link</a></p>',
                status=400,
            )
        found, asked_by = redeemed
        if asked_by in APPS:
            code = accounts.app_code(found.id, asked_by, clock())
            back = f"{asked_by}://signed-in?{urlencode({'code': code})}"
            name = APPS[asked_by]
            return page(
                f"<h2>Signed in</h2><p>Back to {name}…</p>"
                f'<p><a class="button" href="{html.escape(back)}">Open {name}</a></p>'
                '<p class="quiet">You can close this tab.</p>'
                f"<script>location.href = {quote_js(back)}</script>"
            )
        return signed_in(request, found.id, request.headers.get("user-agent", "a browser"))

    @app.get("/auth/app", include_in_schema=False)
    def from_app(request: Request, code: str = "") -> Response:
        """The Mac app's window, given the browser's code (H43), signs in with a session of its own."""
        redeemed = accounts.redeem(code, "app", clock())
        if redeemed is None:
            return page('<h2>That sign-in has run out</h2><p><a class="button" href="/signin">Sign in again</a></p>',
                        status=400)  # fmt: skip
        found, asked_by = redeemed
        return signed_in(request, found.id, f"{APPS.get(asked_by or '', 'Mac app')} on a Mac")

    @app.post("/auth/signout", include_in_schema=False)
    def sign_out(request: Request) -> Response:
        if from_elsewhere(request):
            return JSONResponse({"field": "origin", "message": "Friday takes changes only from its own pages"}, 403)
        accounts.end_session(request.cookies.get(COOKIE), clock())
        response = RedirectResponse("/signin", status_code=303)
        response.delete_cookie(COOKIE, path="/", secure=secure(request), httponly=True, samesite="lax")
        response.headers["Clear-Site-Data"] = '"cache", "storage"'  # the service worker's copies of your plan
        return response

    @app.get("/auth/me", include_in_schema=False)
    def me(request: Request) -> JSONResponse:
        found = accounts.session(request.cookies.get(COOKIE), clock())
        assert found is not None  # the guard let it through
        return JSONResponse({"email": found.email, "username": found.username, "name": found.name})

    def signed_in(request: Request, account_id: int, device: str) -> Response:
        token = accounts.start_session(account_id, device, clock())
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, token, max_age=FOREVER, path="/", secure=secure(request), httponly=True,
                            samesite="lax")  # fmt: skip
        return response


def quote_js(text: str) -> str:
    return '"' + quote(text, safe=":/?=&%-_.~") + '"'


def form(app: str, email: str = "", error: str = "") -> str:
    asked = f'<input type="hidden" name="app" value="{html.escape(app)}">' if app else ""
    said = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    note = f"<p>Signing in {APPS[app]}: the link you're sent brings you back to it.</p>" if app else ""
    return (
        f"<h2>Sign in</h2>{note}{said}"
        '<form method="post" action="/signin">'
        '<label for="email">Your email</label>'
        f'<input id="email" name="email" type="email" autocomplete="email" required autofocus '
        f'value="{html.escape(email)}">{asked}'
        '<button class="button" type="submit">Email me a link</button></form>'
        '<p class="quiet">No password: Friday emails you a link that signs you in.</p>'
    )


def page(body: str, status: int = 200) -> HTMLResponse:
    """A sign-in page in Friday's paper and ink (H56): flat, no gradients, readable greys, nothing under 11px."""
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Sign in · Friday</title>
<meta name="color-scheme" content="light dark"><style>
:root {{ --desk: #efe9dc; --leaf: #fbf8f1; --ink: #1d2a4a; --text: #22252b; --quiet: #5a5f69; --rule: #d9d1c0;
  --red: #b3261e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --desk: #16181d; --leaf: #1f2228; --ink: #a9bdf0; --text: #e9e6df;
  --quiet: #a3a7b0; --rule: #343841; --red: #f2a49d; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--desk); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; padding: 24px; }}
main {{ width: 100%; max-width: 380px; background: var(--leaf); border: 1px solid var(--rule); border-radius: 10px;
  padding: 28px; }}
h1 {{ font: 600 22px/1 "New York", "Source Serif 4", Georgia, serif; color: var(--ink); margin: 0 0 18px; }}
h2 {{ font: 600 18px/1.3 "New York", "Source Serif 4", Georgia, serif; margin: 0 0 10px; }}
label {{ display: block; font-size: 13px; color: var(--quiet); margin: 14px 0 4px; }}
input {{ width: 100%; font: inherit; padding: 9px 10px; border: 1px solid var(--rule); border-radius: 6px;
  background: var(--desk); color: var(--text); }}
input:focus-visible, .button:focus-visible, a:focus-visible {{ outline: 2px solid var(--ink); outline-offset: 2px; }}
.button {{ display: inline-block; margin-top: 14px; font: 600 14px/1 ui-monospace, "SF Mono", Menlo, monospace;
  padding: 11px 14px; border-radius: 6px; border: 0; background: var(--ink); color: var(--leaf); cursor: pointer;
  text-decoration: none; }}
form .button {{ width: 100%; }}
a {{ color: var(--ink); }}
.quiet {{ color: var(--quiet); font-size: 13px; }}
.error {{ color: var(--red); }}
</style></head><body><main><h1>Friday</h1>{body}</main></body></html>""",
        status_code=status,
    )
