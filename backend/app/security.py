"""Authentication, sessions, CSRF, password policy, rate limiting.

Design (Netlify static frontend + Render API):
* Session = random 256-bit token in an HttpOnly cookie; only its SHA-256 is stored, so a DB leak cannot be replayed.
  Idle and absolute expiry are enforced server-side; logout, password change and account deletion revoke sessions.
* The same cookie identifies anonymous visitors (guest carts). Logging in mints a NEW token (no session fixation).
* CSRF: every state-changing request must carry X-CSRF-Token = HMAC(SECRET_KEY, cookie token) obtained from GET /api/auth/me.
  Requests with an Origin header must also come from an allowed origin. Cookies are SameSite=Lax (Netlify proxy mode) or None+Secure (cross-origin mode).
* Passwords: scrypt (Werkzeug), policy checks, constant-time dummy verification for unknown emails, DB lockout, per-IP limits.
"""
import base64
import datetime as dt
import functools
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

from flask import current_app, g, request
from sqlalchemy import delete, select
from werkzeug.security import check_password_hash, generate_password_hash

from .http import cfg, db, error, ext
from .models import AuthSession, User, utcnow

COOKIE = "verity_sid"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
COMMON = frozenset("""password password1 password123 12345678 123456789 1234567890 qwertyui qwerty123 iloveyou admin123 welcome1 letmein1
abc12345 11111111 00000000 passw0rd p@ssw0rd monkey123 dragon123 football1 baseball1 sunshine1 princess1 changeme verity123""".split())
_DUMMY = generate_password_hash("not-a-real-password")


# ------------------------------------------------------------ validation / hashing
def normalise_email(v) -> str:
    return str(v or "").strip().lower()


def valid_email(v: str) -> bool:
    return len(v) <= 254 and bool(EMAIL_RE.match(v))


def password_problem(pw, email: str = "", name: str = "") -> str | None:
    if not isinstance(pw, str) or len(pw) < 8:
        return "Use at least 8 characters."
    if len(pw) > 128:
        return "Use at most 128 characters."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Include at least one letter and one number."
    low = pw.lower()
    if low in COMMON:
        return "That password is too common. Choose something less guessable."
    local = email.split("@")[0]
    if (len(local) >= 4 and local in low) or (name and len(name) >= 4 and name.lower() in low):
        return "Don't include your name or email in your password."
    return None


def hash_password(pw: str) -> str:
    return generate_password_hash(pw)


def verify_password(user: User | None, pw: str) -> bool:
    if user is None:
        check_password_hash(_DUMMY, pw or "")      # same work for unknown emails, so timing doesn't reveal accounts
        return False
    return check_password_hash(user.password_hash, pw or "")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_for(token: str) -> str:
    mac = hmac.new(cfg("SECRET_KEY").encode(), b"csrf:" + token.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")[:43]


# ------------------------------------------------------------ identity
def _read_cookie() -> str:
    t = request.cookies.get(COOKIE, "")
    return t if 20 <= len(t) <= 80 and re.fullmatch(r"[A-Za-z0-9_\-]+", t) else ""


def identity():
    """Resolves (and caches on g) the visitor: cookie token, optional AuthSession and User."""
    if "ident" in g:
        return g.ident
    token, user, sess, minted = _read_cookie(), None, None, False
    if not token:
        token, minted = new_token(), True
    else:
        s = db()
        now = utcnow()
        sess = s.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
        if sess:
            idle = dt.timedelta(days=cfg("SESSION_IDLE_DAYS"))
            if sess.expires_at <= now or sess.last_seen_at + idle <= now:
                s.delete(sess)
                s.commit()
                sess = None
            else:
                u = s.get(User, sess.user_id)
                if u and u.is_active:
                    user = u
                    if now - sess.last_seen_at > dt.timedelta(minutes=5):
                        sess.last_seen_at = now
                        s.commit()
                else:
                    sess = None
    g.ident = {"token": token, "user": user, "session": sess, "minted": minted, "set_cookie": minted}
    return g.ident


def current_user() -> User | None:
    return identity()["user"]


def guest_key() -> str:
    return token_hash(identity()["token"])


def ensure_cookie():
    """Call from routes that need a stable anonymous identity (cart, bootstrap)."""
    identity()["set_cookie"] = True


def start_session(user: User) -> str:
    """Create a fresh session for `user`, replacing the cookie token (prevents session fixation)."""
    s = db()
    token = new_token()
    now = utcnow()
    s.add(AuthSession(token_hash=token_hash(token), user_id=user.id, created_at=now, last_seen_at=now,
                      expires_at=now + dt.timedelta(days=cfg("SESSION_MAX_DAYS"))))
    s.execute(delete(AuthSession).where(AuthSession.expires_at <= now))      # opportunistic cleanup
    g.ident = {"token": token, "user": user, "session": None, "minted": True, "set_cookie": True}
    return token


def end_session():
    ident = identity()
    if ident["session"]:
        db().delete(ident["session"])
    g.ident = {"token": new_token(), "user": None, "session": None, "minted": True, "set_cookie": True}


def revoke_sessions(user_id: int, keep_hash: str | None = None):
    q = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep_hash:
        q = q.where(AuthSession.token_hash != keep_hash)
    db().execute(q)


def apply_cookie(resp):
    ident = g.get("ident")
    if ident and ident.get("set_cookie"):
        resp.set_cookie(COOKIE, ident["token"], max_age=int(cfg("SESSION_MAX_DAYS") * 86400), httponly=True, path="/",
                        secure=cfg("COOKIE_SECURE") or cfg("COOKIE_SAMESITE").lower() == "none", samesite=cfg("COOKIE_SAMESITE"))
    return resp


def clear_cookie(resp):
    resp.delete_cookie(COOKIE, path="/", secure=cfg("COOKIE_SECURE"), samesite=cfg("COOKIE_SAMESITE"))
    return resp


# ------------------------------------------------------------ CSRF / origin
def allowed_origins() -> set[str]:
    origins = {o.rstrip("/") for o in cfg("CORS_ORIGINS")}
    if cfg("PUBLIC_URL"):
        origins.add(cfg("PUBLIC_URL"))
    origins.add(request.host_url.rstrip("/"))
    return origins


def csrf_exempt(f):
    f._csrf_exempt = True
    return f


def check_csrf():
    """Global before_request hook for mutating /api calls."""
    if request.method in ("GET", "HEAD", "OPTIONS") or not request.path.startswith("/api/"):
        return None
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin not in allowed_origins():
        return error(403, "bad_origin", "This request came from an origin that isn't allowed.")
    view = request.url_rule and request.url_rule.endpoint
    fn = view and current_app.view_functions.get(view)
    if fn is not None and getattr(fn, "_csrf_exempt", False):
        return None
    token = _read_cookie()
    sent = request.headers.get("X-CSRF-Token", "")
    if not token or not sent or not hmac.compare_digest(sent, csrf_for(token)):
        return error(403, "csrf", "Your session check failed. Refresh the page and try again.")
    return None


# ------------------------------------------------------------ decorators
def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **k):
        if current_user() is None:
            return error(401, "unauthenticated", "Please sign in to continue.")
        return f(*a, **k)
    return wrapper


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*a, **k):
        u = current_user()
        if u is None:
            return error(401, "unauthenticated", "Please sign in to continue.")
        if u.role != "admin":
            return error(403, "forbidden", "Administrator access is required.")
        return f(*a, **k)
    return wrapper


# ------------------------------------------------------------ rate limiting (per process; see README limitations)
def client_ip() -> str:
    hops = max(1, cfg("TRUSTED_PROXY_HOPS"))
    fwd = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
    if fwd:
        return fwd[-hops] if len(fwd) >= hops else fwd[0]     # entries to the right of this hop were appended by trusted proxies
    return request.remote_addr or "?"


class RateLimiter:
    def __init__(self):
        self.hits: dict[tuple, deque] = defaultdict(deque)

    def hit(self, bucket: str, key: str, limit: int, window: float = 60.0) -> tuple[bool, int]:
        now = time.time()
        if len(self.hits) > 20000:
            for k in [k for k, q in self.hits.items() if not q or now - q[-1] > window]:
                self.hits.pop(k, None)
        q = self.hits[(bucket, key)]
        while q and now - q[0] > window:
            q.popleft()
        q.append(now)
        return len(q) > limit, int(max(1, window - (now - q[0])))

    def clear(self):
        self.hits.clear()


def rate_limited(bucket: str, setting: str):
    """Decorator: per-IP sliding window using the named setting (requests per minute)."""
    def deco(f):
        @functools.wraps(f)
        def wrapper(*a, **k):
            over, wait = ext().limiter.hit(bucket, client_ip(), cfg(setting))
            if over:
                r = error(429, "rate_limited", "Too many requests. Please wait a moment and try again.")
                r.headers["Retry-After"] = str(wait)
                return r
            return f(*a, **k)
        return wrapper
    return deco


def checkout_gate(f):
    """Order placement is disabled in the demo build (CHECKOUT_ENABLED=0). Applied outermost so even signed-in users get the same clear answer."""
    @functools.wraps(f)
    def wrapper(*a, **k):
        if not cfg("CHECKOUT_ENABLED"):
            return error(403, "checkout_disabled", "Checkout is disabled in this demo. No order can be placed and no payment is taken.")
        return f(*a, **k)
    return wrapper
