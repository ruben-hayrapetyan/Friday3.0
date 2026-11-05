# ruff: noqa: E501  (the scripts below are JavaScript in strings, kept as written rather than wrapped mid-statement)
"""The browser's side of passkeys on the sign-in pages (server/signin.py; H88, H89, H91), plain script with no
library: the email box offering your passkey by autofill, Touch ID asked straight away (H93), and the emailed code's box
(H92). Making a passkey is the website's, through web/src/api/passkeys.ts (Settings, and the bar inside Friday, H94)."""

import json

# Bytes travel as base64url both ways (the server's options, the browser's answers).
COMMON = """
const dec = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const enc = (b) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
const post = (url, body) => fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
  .then((r) => r.json().then((j) => ({ ok: r.ok, j })));
const said = (text) => { const p = document.getElementById("passkey-said"); if (p) { p.textContent = text; p.hidden = false; } };
"""

SIGNIN = """
// Two ways Touch ID is asked. The email box's list: Chrome lists passkeys when the box gains focus while a request
// waits, so the box is focused only after the request starts, and a request that ends (its ten minutes, or set aside)
// is made again (5 Nov: the passkey was saved but never offered). And straight away: by itself on a browser that has
// a passkey, or from the button (H93); the box's request is set aside first, since a browser asks one at a time.
const email = document.getElementById("email");
const button = document.getElementById("passkey-button");
const focus = () => { if (document.activeElement !== email) email.focus(); };
let waiting = null;
async function options() {
  const { ok, j } = await post("/auth/passkey/signin/options", { app: APP });
  if (!ok) return null;
  const o = j.options;
  o.challenge = dec(o.challenge);
  o.allowCredentials = (o.allowCredentials || []).map((c) => ({ ...c, id: dec(c.id) }));
  return { flow: j.flow, o };
}
async function finish(flow, cred) {
  const r = cred.response;
  const answer = await post("/auth/passkey/signin", { flow, credential: {
    id: cred.id, rawId: enc(cred.rawId), type: cred.type, authenticatorAttachment: cred.authenticatorAttachment,
    clientExtensionResults: cred.getClientExtensionResults(),
    response: { clientDataJSON: enc(r.clientDataJSON), authenticatorData: enc(r.authenticatorData),
                signature: enc(r.signature), userHandle: r.userHandle ? enc(r.userHandle) : null } } });
  if (answer.ok) { location.href = answer.j.next; return true; }
  said(answer.j.message || "That passkey didn't work; use the emailed code.");
  return false;
}
async function listen(tries) {
  if (!(await PublicKeyCredential.isConditionalMediationAvailable?.())) { focus(); return; }
  const got = await options();
  if (!got) { focus(); return; }
  const stop = new AbortController();
  waiting = stop;
  const asked = navigator.credentials.get({ publicKey: got.o, mediation: "conditional", signal: stop.signal });
  focus();
  let cred;
  try { cred = await asked; } catch { if (waiting === stop && tries < 20) setTimeout(() => listen(tries + 1), 1000); return; }
  waiting = null;
  if (!(await finish(got.flow, cred))) listen(tries + 1);
}
async function ask() {
  if (waiting) { const stop = waiting; waiting = null; stop.abort(); }
  const got = await options();
  let cred = null;
  if (got) { try { cred = await navigator.credentials.get({ publicKey: got.o }); } catch { cred = null; } }
  if (!cred || !(await finish(got.flow, cred))) listen(0);
}
if (!window.PublicKeyCredential) focus();
else {
  button.hidden = false;
  button.addEventListener("click", ask);
  if (KNOWN) ask(); else listen(0);
}
"""

CODE = """
// Six digits sign in by themselves (H92): the code is the last thing to do, so no click after it.
const box = document.getElementById("code");
let sent = false;
box.addEventListener("input", () => {
  if (!sent && box.value.replace(/\\D/g, "").length === 6) { sent = true; box.form.requestSubmit(); }
});
"""


def signin_script(app: str, known: bool = False) -> str:
    return f"<script>const APP = {json.dumps(app or None)}; const KNOWN = {json.dumps(known)};{COMMON}{SIGNIN}</script>"


def code_script() -> str:
    return f"<script>{CODE}</script>"
