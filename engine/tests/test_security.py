import time

from xahoo.security import LoginLimiter, Sessions, totp, totp_ok


def test_totp_rfc6238_vector():
    # RFC 6238 test vector (SHA-1, secret "12345678901234567890"), truncated to 6 digits
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp(secret, t=59) == "287082"
    assert totp(secret, t=1111111109) == "081804"
    assert totp_ok(secret, totp(secret)) and not totp_ok(secret, "000000" if totp(secret) != "000000" else "111111")


def test_sessions_expire_and_rotate_with_password():
    s = Sessions(b"k", "pw1")
    tok = s.issue()
    assert s.valid(tok)
    assert not Sessions(b"k", "pw2").valid(tok)          # password change logs out
    assert not s.valid(f"{int(time.time()) - 1}.{s._sig(str(int(time.time()) - 1))}")
    assert not s.valid("garbage")


def test_login_lockout():
    lim = LoginLimiter()
    for _ in range(5):
        assert not lim.locked("ip")
        lim.fail("ip")
    assert lim.locked("ip") > 0
    lim.ok("ip")
    assert not lim.locked("ip")
