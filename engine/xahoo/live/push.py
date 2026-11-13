"""Web Push without payload ("tickle" push), so alert contents never pass through Google/Apple/Mozilla.

The push service only wakes the installed app; its service worker then fetches the newest alert from this server
over the owner's logged-in session (`/api/alerts/latest`). Only the VAPID signature is needed (RFC 8292), so there
is no payload encryption to get wrong. Keys live in data/vapid_private.pem (created on first use, mode 600).
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class WebPush:
    def __init__(self, key_path: Path, subject: str | None = None):
        self.key_path = key_path
        self.subject = subject or os.environ.get("XAHOO_VAPID_SUB", "mailto:admin@xahoo.invalid")
        self._key = self._load_or_create()

    def _load_or_create(self) -> ec.EllipticCurvePrivateKey:
        if self.key_path.exists():
            return serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        key = ec.generate_private_key(ec.SECP256R1())
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()))
        os.chmod(self.key_path, 0o600)
        return key

    @property
    def public_key(self) -> str:
        """applicationServerKey for PushManager.subscribe (uncompressed P-256 point, base64url)."""
        raw = self._key.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint)
        return _b64(raw)

    def _jwt(self, endpoint: str) -> str:
        u = urlparse(endpoint)
        header = _b64(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
        claims = _b64(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                                  "sub": self.subject}, separators=(",", ":")).encode())
        signing_input = f"{header}.{claims}".encode()
        r, s = decode_dss_signature(self._key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
        return f"{header}.{claims}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"

    def send(self, subscription: dict, ttl: int = 3600) -> int:
        """Wake one subscribed device. Returns the HTTP status (404/410 = subscription is gone)."""
        endpoint = subscription["endpoint"]
        headers = {"Authorization": f"vapid t={self._jwt(endpoint)}, k={self.public_key}",
                   "TTL": str(ttl), "Urgency": "high", "Content-Length": "0"}
        return requests.post(endpoint, headers=headers, timeout=10).status_code
