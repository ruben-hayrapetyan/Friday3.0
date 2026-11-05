# ruff: noqa: E501  (the scripts below are JavaScript in strings, kept as written rather than wrapped mid-statement)
"""The browser's side of passkeys on the sign-in pages (server/signin.py; H88, H89, H91), plain script with no
library: the email box offering your passkey by autofill, and the offer to make one after an emailed link. The
website's Settings does the same through web/src/api/passkeys.ts."""

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
(async () => {
  if (!window.PublicKeyCredential?.isConditionalMediationAvailable || !(await PublicKeyCredential.isConditionalMediationAvailable())) return;
  const { ok, j } = await post("/auth/passkey/signin/options", { app: APP });
  if (!ok) return;
  const o = j.options;
  o.challenge = dec(o.challenge);
  o.allowCredentials = (o.allowCredentials || []).map((c) => ({ ...c, id: dec(c.id) }));
  let cred;
  try { cred = await navigator.credentials.get({ publicKey: o, mediation: "conditional" }); } catch { return; }
  const r = cred.response;
  const answer = await post("/auth/passkey/signin", { flow: j.flow, credential: {
    id: cred.id, rawId: enc(cred.rawId), type: cred.type, authenticatorAttachment: cred.authenticatorAttachment,
    clientExtensionResults: cred.getClientExtensionResults(),
    response: { clientDataJSON: enc(r.clientDataJSON), authenticatorData: enc(r.authenticatorData),
                signature: enc(r.signature), userHandle: r.userHandle ? enc(r.userHandle) : null } } });
  if (answer.ok) location.href = answer.j.next; else said(answer.j.message || "That passkey didn't work; use the email link.");
})();
"""

OFFER = """
if (!window.PublicKeyCredential) location.replace("/");
document.getElementById("add-passkey").addEventListener("click", async (event) => {
  event.target.disabled = true;
  const { ok, j } = await post("/auth/passkey/register/options", {});
  if (!ok) { said(j.message || "Couldn't start; try again from Settings."); event.target.disabled = false; return; }
  const o = j.options;
  o.challenge = dec(o.challenge);
  o.user.id = dec(o.user.id);
  o.excludeCredentials = (o.excludeCredentials || []).map((c) => ({ ...c, id: dec(c.id) }));
  let cred;
  try { cred = await navigator.credentials.create({ publicKey: o }); }
  catch { said("No passkey made. You can add one later in Settings → About you."); event.target.disabled = false; return; }
  const r = cred.response;
  const answer = await post("/auth/passkey/register", { flow: j.flow, credential: {
    id: cred.id, rawId: enc(cred.rawId), type: cred.type, authenticatorAttachment: cred.authenticatorAttachment,
    clientExtensionResults: cred.getClientExtensionResults(),
    response: { clientDataJSON: enc(r.clientDataJSON), attestationObject: enc(r.attestationObject),
                transports: r.getTransports ? r.getTransports() : [] } } });
  if (answer.ok) location.replace("/"); else { said(answer.j.message); event.target.disabled = false; }
});
"""


def signin_script(app: str) -> str:
    return f"<script>const APP = {json.dumps(app or None)};{COMMON}{SIGNIN}</script>"


def offer_body() -> str:
    return (
        "<h2>Use Touch ID next time?</h2>"
        "<p>Save a passkey on this device, and next time sign in with Touch ID instead of waiting for an email.</p>"
        '<p class="error" id="passkey-said" role="alert" hidden></p>'
        '<button class="button" id="add-passkey" type="button">Add a passkey</button>'
        '<p class="quiet"><a href="/auth/passkey/later">Not now</a> · You can add one any time in Settings → About'
        " you.</p>"
        f"<script>{COMMON}{OFFER}</script>"
    )
