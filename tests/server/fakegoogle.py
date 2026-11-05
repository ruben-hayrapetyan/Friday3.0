"""Google's sign-in, played locally for tests (server/google_signin.py): a token endpoint that answers a code with an
ID token signed by its own RSA key, and the key published as Google publishes its certificates. The test says what
the token claims, and can read what the token request carried (the PKCE verifier)."""

import datetime
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt, jwt

CLIENT_ID = "friday-test-client.apps.googleusercontent.com"


class FakeGoogle:
    def __init__(self) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fake-google")])
        now = datetime.datetime.now(datetime.UTC)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))  # fmt: skip
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()  # fmt: skip
        self.signer = crypt.RSASigner.from_string(pem, key_id="k1")
        self.certs = {"k1": cert.public_bytes(serialization.Encoding.PEM).decode()}
        self.claims: dict[str, Any] = {}
        self.requests: list[dict[str, str]] = []
        self.refuse = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def answer(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                self.answer(200, fake.certs)

            def do_POST(self) -> None:  # noqa: N802
                form = {
                    k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["content-length"])).decode()).items()
                }
                fake.requests.append(form)
                if fake.refuse:
                    return self.answer(400, {"error": "invalid_grant"})
                self.answer(200, {"id_token": fake.token()})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def token(self) -> str:
        now = int(time.time())
        body = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "1234", "iat": now, "exp": now + 600,
                "email_verified": True} | self.claims  # fmt: skip
        return jwt.encode(self.signer, body).decode()

    def environment(self) -> dict[str, str]:
        return {"FRIDAY_GOOGLE_CLIENT_ID": CLIENT_ID, "FRIDAY_GOOGLE_CLIENT_SECRET": "test-secret",
                "FRIDAY_GOOGLE_TOKEN_URL": f"{self.url}/token", "FRIDAY_GOOGLE_CERTS_URL": f"{self.url}/certs",
                "FRIDAY_GOOGLE_AUTHORIZE_URL": f"{self.url}/authorize"}  # fmt: skip

    def stop(self) -> None:
        self.server.shutdown()
