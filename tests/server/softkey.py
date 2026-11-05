"""A passkey authenticator in software, for tests: makes a P-256 key, answers `navigator.credentials.create` and
`.get` as a browser with Touch ID would (attestation "none"), as the JSON the pages post."""

import hashlib
import json
import os
import struct
from dataclasses import dataclass, field

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url


@dataclass
class SoftKey:
    origin: str
    rp_id: str
    key: ec.EllipticCurvePrivateKey = field(default_factory=lambda: ec.generate_private_key(ec.SECP256R1()))
    credential_id: bytes = field(default_factory=lambda: os.urandom(16))
    count: int = 0
    user_handle: bytes = b""

    def client_data(self, kind: str, challenge: str, origin: str | None = None) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin or self.origin}).encode()

    def auth_data(self, attested: bytes = b"", flags: int = 0x05) -> bytes:  # user present + verified
        self.count += 1
        return hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", self.count) + attested

    def create(self, options: dict, origin: str | None = None) -> dict:
        """`navigator.credentials.create` for these options."""
        self.user_handle = base64url_to_bytes(options["user"]["id"])
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})
        attested = bytes(16) + struct.pack(">H", len(self.credential_id)) + self.credential_id + cose
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": self.auth_data(attested, 0x45)})
        cid = bytes_to_base64url(self.credential_id)
        return {
            "id": cid,
            "rawId": cid,
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(self.client_data("webauthn.create", options["challenge"], origin)),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
        }

    def get(self, options: dict, origin: str | None = None) -> dict:
        """`navigator.credentials.get` for these options."""
        data = self.auth_data()
        client = self.client_data("webauthn.get", options["challenge"], origin)
        signature = self.key.sign(data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        cid = bytes_to_base64url(self.credential_id)
        return {
            "id": cid,
            "rawId": cid,
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(client),
                "authenticatorData": bytes_to_base64url(data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(self.user_handle),
            },
        }
