"""Private single-owner access: signed expiring sessions, optional TOTP 2-step code, login lockout,
no-index / privacy headers. Pure standard library."""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from collections import defaultdict, deque

SESSION_DAYS = 30
LOCK_FAILS, LOCK_WINDOW = 5, 15 * 60

# Search engines, archivers, embedding and referrers: all off. Everything is served from this origin only.
PRIVACY_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet, noimageindex, notranslate",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data:; font-src 'self'; connect-src 'self'; worker-src 'self'; "
                                "manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
}
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


class Sessions:
    """Token = '<expiry>.<hmac(secret, expiry | password-hash)>'. Changing the password logs out every device."""

    def __init__(self, secret: bytes, password: str):
        self.secret = secret
        self.pw_hash = hashlib.sha256(password.encode()).hexdigest()

    def issue(self, days: int = SESSION_DAYS) -> str:
        exp = str(int(time.time()) + days * 86400)
        return f"{exp}.{self._sig(exp)}"

    def valid(self, token: str) -> bool:
        try:
            exp, sig = token.split(".", 1)
            return int(exp) > time.time() and hmac.compare_digest(sig, self._sig(exp))
        except (ValueError, AttributeError):
            return False

    def _sig(self, exp: str) -> str:
        return hmac.new(self.secret, f"{exp}|{self.pw_hash}".encode(), hashlib.sha256).hexdigest()


def totp(secret_b32: str, t: float | None = None, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 TOTP (SHA-1), compatible with Google Authenticator / Authy / 1Password."""
    key = base64.b32decode(secret_b32.upper().replace(" ", "") + "=" * (-len(secret_b32.replace(" ", "")) % 8))
    counter = int((time.time() if t is None else t) // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits)


def totp_ok(secret_b32: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    now = time.time()
    return any(hmac.compare_digest(totp(secret_b32, now + k * 30), code) for k in range(-window, window + 1))


class LoginLimiter:
    """At most LOCK_FAILS failed logins per client per LOCK_WINDOW seconds."""

    def __init__(self):
        self.fails: dict[str, deque] = defaultdict(deque)

    def locked(self, who: str) -> int:
        q = self.fails[who]
        while q and q[0] < time.time() - LOCK_WINDOW:
            q.popleft()
        return int(q[0] + LOCK_WINDOW - time.time()) if len(q) >= LOCK_FAILS else 0

    def fail(self, who: str) -> None:
        self.fails[who].append(time.time())

    def ok(self, who: str) -> None:
        self.fails.pop(who, None)


def new_totp_secret() -> str:
    import secrets
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


if __name__ == "__main__":
    sec = new_totp_secret()
    print("XAHOO_TOTP_SECRET=" + sec)
    print("Add it to your authenticator app (Google Authenticator / Authy / 1Password) with 'Enter a setup key',")
    print("type: time-based, or open this link on the phone:")
    print(f"otpauth://totp/XAHOO:owner?secret={sec}&issuer=XAHOO&digits=6&period=30")
