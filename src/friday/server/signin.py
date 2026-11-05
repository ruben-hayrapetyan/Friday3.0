"""Signing in and out of a hosted Friday (HOSTED.md S4, H81–H95): every page and API call needs a session (H83),
except these pages. The emailed code, typed where you asked, or the email's link (H22, H92) signs this browser in
until you sign out (H25); asked from the Mac app (H43, H95), the browser instead hands the app a one-time code, which
the app's window trades for a session of its own.

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
from friday.server.accounts import Account, Accounts
from friday.server.google_signin import Client, GoogleError, GoogleSignIn
from friday.server.passkey_page import code_script, signin_script
from friday.server.passkeys import Party, PasskeyError, Passkeys, device_name

COOKIE = "friday_session"
FOREVER = 10 * 365 * 24 * 3600  # "until you sign out" (H25)
OPEN = (
    "/signin",
    "/signin/code",
    "/auth/link",
    "/auth/app",
    "/auth/passkey/signin/options",
    "/auth/google/start",
    "/auth/google",
    "/auth/passkey/signin",
    "/manifest.webmanifest",
    "/icon-192.png",
    "/icon-512.png",
)
OFFERED = "friday_passkey"  # "made": this browser has a passkey (Touch ID asks by itself, H93); "later": Not now
APPS = {"friday-test": "Friday Test", "friday": "Friday"}  # the Mac apps that may ask, by their link scheme


def install(app: FastAPI, accounts: Accounts, clock: Callable[[], int], foreign: Callable[..., bool]) -> None:
    """The sign-in pages and the guard in front of everything else."""

    def public(request: Request) -> str:
        return os.environ.get("FRIDAY_PUBLIC_URL", str(request.base_url)).rstrip("/")

    def secure(request: Request) -> bool:
        return public(request).startswith("https://")

    def from_elsewhere(request: Request) -> bool:
        return foreign(request.headers.get("origin"), request.headers.get("host"))

    keys = Passkeys(accounts)
    client = Client.from_environment()
    google = GoogleSignIn(accounts, client) if client else None

    def party(request: Request) -> Party:
        return Party.of(public(request))

    def who(request: Request) -> Account:
        found = accounts.session(request.cookies.get(COOKIE), clock())
        assert found is not None  # the guard let it through
        return found

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
        known = request.cookies.get(OFFERED) == "made"
        return page(form(app if app in APPS else "", google=google is not None, known=known))

    @app.post("/signin", include_in_schema=False)
    def send_link(request: Request, email: str = Form(""), app: str = Form("")) -> Response:
        if from_elsewhere(request):
            return page("<p>Friday takes sign-ins only from its own page.</p>", status=403)
        app = app if app in APPS else ""
        flow, code = accounts.emailed_code(email, clock(), app or None)
        made = accounts.email_link(email, clock(), app or None)
        if made is not None:
            found, token = made
            accounts.pair(flow, token)
            try:
                outgoing.send(outgoing.signin_message(found.email, f"{public(request)}/auth/link?t={token}", code))
            except outgoing.MailError as error:
                return page(form(app, email, str(error), google is not None), status=503)
        # The same answer whether or not the address has an account, so the page tells nobody who does.
        return page(code_form(email, flow, app))

    @app.post("/signin/code", include_in_schema=False)
    def type_code(request: Request, flow: str = Form(""), code: str = Form(""), email: str = Form(""),
                  app: str = Form("")) -> Response:  # fmt: skip
        """The emailed code typed on the page that asked (H92): signed in where you are, without opening the email."""
        if from_elsewhere(request):
            return page("<p>Friday takes sign-ins only from its own page.</p>", status=403)
        redeemed = accounts.redeem_code(flow, code, clock())
        if isinstance(redeemed, str):
            return page(code_form(email, flow, app if app in APPS else "", redeemed), status=400)
        found, asked_by = redeemed
        if asked_by in APPS:
            return hand_back(asked_by, accounts.app_code(found.id, asked_by, clock()))
        return signed_in(request, found.id, request.headers.get("user-agent", "a browser"))

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
            return hand_back(asked_by, accounts.app_code(found.id, asked_by, clock()))
        return signed_in(request, found.id, request.headers.get("user-agent", "a browser"))

    @app.get("/auth/google/start", include_in_schema=False)
    def google_start(request: Request, app: str = "") -> Response:
        if google is None:
            return page("<h2>Sign in with Google isn't set up here yet</h2>", status=404)
        where = google.start(f"{public(request)}/auth/google", clock(), app if app in APPS else None)
        return RedirectResponse(where, status_code=303)

    @app.get("/auth/google", include_in_schema=False)
    def google_back(request: Request, code: str = "", state: str = "", error: str = "") -> Response:
        if google is None:
            return page("<h2>Sign in with Google isn't set up here yet</h2>", status=404)
        again = '<p><a class="button" href="/signin">Back to sign in</a></p>'
        if error or not code:  # Cancel on Google's page
            return page(f"<h2>Not signed in</h2>{again}", status=400)
        try:
            email, asked_by = google.finish(code, state, f"{public(request)}/auth/google", clock())
        except GoogleError as failed:
            return page(f"<h2>Not signed in</h2><p>{html.escape(str(failed))}</p>{again}", status=400)
        found = accounts.by_email(email)
        if found is None:  # invites only (H24)
            return page(
                f"<h2>No Friday account for {html.escape(email)}</h2><p>Friday is by invitation for now. Use the "
                f"Google account with your Friday email.</p>{again}",
                status=403,
            )
        if asked_by in APPS:
            return hand_back(asked_by, accounts.app_code(found.id, asked_by, clock()))
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
        # "Use Touch ID next time?" shows inside Friday until this browser has a passkey or says Not now (H94).
        offer = not request.cookies.get(OFFERED)
        mine = {"email": found.email, "username": found.username, "name": found.name}
        return JSONResponse(mine | {"offer_passkey": offer})

    def signed_in(request: Request, account_id: int, device: str, response: Response | None = None) -> Response:
        token = accounts.start_session(account_id, device, clock())
        response = response or RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, token, max_age=FOREVER, path="/", secure=secure(request), httponly=True,
                            samesite="lax")  # fmt: skip
        return response

    def remember(request: Request, response: Response, value: str) -> Response:
        response.set_cookie(OFFERED, value, max_age=FOREVER, path="/", secure=secure(request), httponly=True,
                            samesite="lax")  # fmt: skip
        return response

    def refused(error: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"field": "passkey", "message": error}, status_code=status)

    @app.post("/auth/passkey/later", include_in_schema=False)
    def later(request: Request) -> Response:
        """Not now, on the bar inside Friday (H94): this browser isn't asked again."""
        if from_elsewhere(request):
            return refused("Friday takes changes only from its own pages", 403)
        return remember(request, JSONResponse({"offer_passkey": False}), "later")

    @app.post("/auth/passkey/register/options", include_in_schema=False)
    def register_options(request: Request) -> Response:
        if from_elsewhere(request):
            return refused("Friday takes changes only from its own pages", 403)
        return JSONResponse(keys.registration_options(who(request), party(request), clock()))

    @app.post("/auth/passkey/register", include_in_schema=False)
    async def register(request: Request) -> Response:
        if from_elsewhere(request):
            return refused("Friday takes changes only from its own pages", 403)
        body = await request.json()
        try:
            name = device_name(request.headers.get("user-agent", ""))
            flow, credential = str(body.get("flow", "")), body.get("credential") or {}
            made = keys.register(who(request), flow, credential, name, party(request), clock())
        except PasskeyError as error:
            return refused(str(error))
        return remember(request, JSONResponse({"id": made.id, "name": made.name}), "made")

    @app.post("/auth/passkey/signin/options", include_in_schema=False)
    async def signin_options(request: Request) -> Response:
        if from_elsewhere(request):
            return refused("Friday takes sign-ins only from its own page", 403)
        app_name = str((await request.json() or {}).get("app") or "")
        return JSONResponse(keys.signin_options(party(request), clock(), app_name if app_name in APPS else None))

    @app.post("/auth/passkey/signin", include_in_schema=False)
    async def passkey_signin(request: Request) -> Response:
        if from_elsewhere(request):
            return refused("Friday takes sign-ins only from its own page", 403)
        body = await request.json()
        try:
            found, asked_by = keys.signin(str(body.get("flow", "")), body.get("credential") or {}, party(request),
                                          clock())  # fmt: skip
        except PasskeyError as error:
            return refused(str(error))
        # This browser has a passkey from now on, however it came to have one: Touch ID asks by itself (H93).
        if asked_by in APPS:  # the browser page Friday Test opened (H91): hand back as the link does
            code = accounts.app_code(found.id, asked_by, clock())
            back = JSONResponse({"next": f"{asked_by}://signed-in?{urlencode({'code': code})}"})
            return remember(request, back, "made")
        device = request.headers.get("user-agent", "a browser")
        return remember(request, signed_in(request, found.id, device, JSONResponse({"next": "/"})), "made")

    @app.get("/auth/passkeys", include_in_schema=False)
    def passkey_list(request: Request) -> JSONResponse:
        mine = keys.of(who(request).id)
        return JSONResponse([{"id": p.id, "name": p.name, "created": p.created, "used": p.used} for p in mine])

    @app.post("/auth/passkeys/remove", include_in_schema=False)
    async def passkey_remove(request: Request) -> Response:
        if from_elsewhere(request):
            return refused("Friday takes changes only from its own pages", 403)
        passkey_id = str((await request.json() or {}).get("id", ""))
        account_id = who(request).id
        response = JSONResponse({"removed": keys.remove(account_id, passkey_id)})
        if not keys.of(account_id):  # none left: Touch ID can't ask by itself, and the offer comes back (H93, H94)
            response.delete_cookie(OFFERED, path="/", secure=secure(request), httponly=True, samesite="lax")
        return response


def hand_back(asked_by: str, code: str) -> HTMLResponse:
    """The browser page that hands a sign-in back to the Mac app that asked (H43)."""
    back = f"{asked_by}://signed-in?{urlencode({'code': code})}"
    name = APPS[asked_by]
    return page(
        f"<h2>Signed in</h2><p>Back to {name}…</p>"
        f'<p><a class="button" href="{html.escape(back)}">Open {name}</a></p>'
        '<p class="quiet">You can close this tab.</p>'
        f"<script>location.href = {quote_js(back)}</script>"
    )


def quote_js(text: str) -> str:
    return '"' + quote(text, safe=":/?=&%-_.~") + '"'


def form(app: str, email: str = "", error: str = "", google: bool = False, known: bool = False) -> str:
    asked = f'<input type="hidden" name="app" value="{html.escape(app)}">' if app else ""
    said = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    note = f"<p>Signing in {APPS[app]}: the link you're sent brings you back to it.</p>" if app else ""
    return (
        f"<h2>Sign in</h2>{note}{said}"
        '<form method="post" action="/signin">'
        '<label for="email">Your email</label>'
        f'<input id="email" name="email" type="email" autocomplete="username webauthn" required '
        f'value="{html.escape(email)}">{asked}'
        '<button class="button" type="submit">Email me a code</button></form>'
        + (
            f'<a class="button other" href="/auth/google/start{"?app=" + app if app else ""}">Continue with Google</a>'
            if google
            else ""
        )
        + '<button class="button other" id="passkey-button" type="button" hidden>Sign in with Touch ID</button>'
        '<p class="error" id="passkey-said" role="alert" hidden></p>'
        '<p class="quiet">No password: Friday emails you a code, or Touch ID signs you in.</p>'
        + signin_script(app, known)
    )


def code_form(email: str, flow: str, app: str, error: str = "") -> str:
    """Where the emailed code is typed (H92); six digits sign in by themselves, without a click."""
    said = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    keep = (f'<input type="hidden" name="email" value="{html.escape(email.strip())}">'
            + (f'<input type="hidden" name="app" value="{html.escape(app)}">' if app else ""))  # fmt: skip
    return (
        f"<h2>Check your email</h2><p>If <b>{html.escape(email.strip())}</b> has a Friday account, a code is on its "
        "way. Type it here, or open the link in the email.</p>"
        f'{said}<form method="post" action="/signin/code"><label for="code">6-digit code</label>'
        '<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="7" '
        f'pattern="[0-9 ]{{6,7}}" required autofocus>{keep}'
        f'<input type="hidden" name="flow" value="{html.escape(flow)}">'
        '<button class="button" type="submit">Sign in</button></form>'
        f'<form method="post" action="/signin">{keep}<p class="quiet">The code and link work once, for 15 minutes. '
        '<button class="linkish" type="submit">Send a new code</button> · '
        f'<a href="/signin{"?app=" + app if app else ""}">Use another address</a></p></form>' + code_script()
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
form .button, .button.other {{ width: 100%; text-align: center; }}
.button.other {{ background: transparent; color: var(--ink); border: 1px solid var(--rule); }}
.button[hidden] {{ display: none; }}
#code {{ font: 600 22px/1.2 ui-monospace, "SF Mono", Menlo, monospace; letter-spacing: 0.3em; text-align: center; }}
.linkish {{ font: inherit; color: var(--ink); background: none; border: 0; padding: 0; text-decoration: underline;
  cursor: pointer; }}
a {{ color: var(--ink); }}
.quiet {{ color: var(--quiet); font-size: 13px; }}
.error {{ color: var(--red); }}
</style></head><body><main><h1>Friday</h1>{body}</main></body></html>""",
        status_code=status,
    )
