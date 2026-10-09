"""Dependency-free password hashing + HS256 JWT."""
import base64, hashlib, hmac, json, os, time
def _secret():
    env = os.environ.get("DT_SECRET")
    if env:
        if len(env) < 32: raise SystemExit("DT_SECRET must be at least 32 characters (e.g. `openssl rand -hex 32`)")
        return env.encode()
    from .db import DATA                       # zero-config: generate once, keep in data/.secret (chmod 600)
    f = os.path.join(DATA, ".secret")
    if not os.path.exists(f):
        with open(os.open(f, os.O_WRONLY | os.O_CREAT, 0o600), "w") as h: h.write(os.urandom(32).hex())
    return open(f).read().strip().encode()
SECRET = _secret()
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
unb64 = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def hash_pw(pw, salt=None):
    salt = salt or os.urandom(16)
    return b64(salt) + "$" + b64(hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000))

def check_pw(pw, stored):
    s, _ = stored.split("$")
    return hmac.compare_digest(hash_pw(pw, unb64(s)), stored)

def make_token(uid, ttl=7 * 86400):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": uid, "exp": int(time.time()) + ttl}).encode())
    return f"{h}.{p}.{b64(hmac.new(SECRET, f'{h}.{p}'.encode(), hashlib.sha256).digest())}"

def read_token(tok):
    try:
        h, p, s = tok.split(".")
        if not hmac.compare_digest(s, b64(hmac.new(SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest())):
            return None
        d = json.loads(unb64(p))
        return d["sub"] if d["exp"] > time.time() else None
    except Exception:
        return None
