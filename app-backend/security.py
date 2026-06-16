"""Authentication & hardening primitives.

- Argon2id password hashing (argon2-cffi defaults tuned upward)
- Database-backed sessions: the browser holds a random 256-bit token in an
  httpOnly/SameSite cookie; only its SHA-256 hash is stored at rest, so a
  leaked database cannot be replayed into live sessions.
- CSRF: synchronizer token kept in Flask's signed cookie session, required
  on every POST, compared in constant time.
- Same-origin enforcement on mutating requests (Origin/Referer check).
- In-memory sliding-window rate limiting for login/register/price refresh.
"""
import hashlib
import hmac
import re
import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import (abort, current_app, flash, g, redirect, request, session,
                   url_for)

from .db import get_db

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

SESSION_COOKIE = "cairn_session"
SESSION_LIFETIME = timedelta(days=14)
SLIDING_REFRESH = timedelta(hours=1)

# A timing-equalizing dummy hash: verifying against this when the email is
# unknown keeps login latency identical for real and fake accounts.
_DUMMY_HASH = _hasher.hash("not-a-real-password-3f9a")

COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123", "passw0rd",
    "123456", "1234567", "12345678", "123456789", "1234567890",
    "qwerty", "qwerty123", "qwertyuiop", "letmein", "welcome", "welcome1",
    "iloveyou", "admin", "administrator", "abc123", "monkey", "dragon",
    "sunshine", "princess", "football", "baseball", "trustno1", "superman",
    "1q2w3e4r", "zaq12wsx", "password!", "p@ssw0rd", "changeme",
}

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(pw_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(pw_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def equalize_timing(password: str) -> None:
    """Burn the same CPU as a real verification (account-enumeration guard)."""
    try:
        _hasher.verify(_DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        pass


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("Password must be at least 10 characters long.")
    if len(password) > 128:
        problems.append("Password must be at most 128 characters long.")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("That password is too common. Pick something unique.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("Use at least one letter and one number.")
    return problems


# ----------------------------------------------------------------- sessions
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def start_session(response, user_id: int):
    """Create a DB session and attach the cookie to the response."""
    token = secrets.token_urlsafe(32)
    db = get_db()
    expires = _utcnow() + SESSION_LIFETIME
    db.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at, user_agent)"
        " VALUES (?, ?, ?, ?)",
        (user_id, _token_hash(token), expires.strftime("%Y-%m-%d %H:%M:%S"),
         (request.user_agent.string or "")[:300]),
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="Lax",
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        path="/",
    )
    return response


def end_session(response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token_hash = ?",
                   (_token_hash(token),))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def revoke_other_sessions(user_id: int, keep_session_id: int | None):
    db = get_db()
    if keep_session_id is None:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    else:
        db.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?",
                   (user_id, keep_session_id))
    db.commit()


def _load_current_user():
    g.user = None
    g.session_id = None
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 128:
        return
    db = get_db()
    row = db.execute(
        "SELECT s.id AS session_id, s.expires_at, s.last_seen, u.*"
        " FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token_hash = ?",
        (_token_hash(token),),
    ).fetchone()
    if row is None:
        return
    now = _utcnow()
    expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
    if expires_at < now:
        db.execute("DELETE FROM sessions WHERE id = ?", (row["session_id"],))
        db.commit()
        return
    last_seen = datetime.strptime(row["last_seen"], "%Y-%m-%d %H:%M:%S")
    if now - last_seen > SLIDING_REFRESH:
        db.execute(
            "UPDATE sessions SET last_seen = ?, expires_at = ? WHERE id = ?",
            (now.strftime("%Y-%m-%d %H:%M:%S"),
             (now + SESSION_LIFETIME).strftime("%Y-%m-%d %H:%M:%S"),
             row["session_id"]),
        )
        db.commit()
    g.user = row
    g.session_id = row["session_id"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def safe_next(target: str | None, fallback: str = "/dashboard") -> str:
    """Only allow local redirect targets (no open redirects)."""
    if not target:
        return fallback
    if target.startswith("/") and not target.startswith("//") \
            and "\\" not in target:
        return target
    return fallback


# --------------------------------------------------------------------- CSRF
def csrf_token() -> str:
    tok = session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf"] = tok
    return tok


def _check_csrf():
    sent = request.form.get("csrf_token", "")
    good = session.get("csrf", "")
    if not good or not sent or not hmac.compare_digest(sent, good):
        abort(403)


def _check_same_origin():
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return  # non-browser client; CSRF token still required
    parsed = urlparse(origin)
    if parsed.netloc and parsed.netloc != request.host:
        abort(403)


# ------------------------------------------------------------- rate limiting
class RateLimiter:
    def __init__(self):
        self._buckets: dict[tuple, deque] = {}

    def allow(self, scope: str, key: str, limit: int, per_seconds: int) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault((scope, key), deque())
        while bucket and bucket[0] <= now - per_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        # opportunistic cleanup so the map can't grow unbounded
        if len(self._buckets) > 10_000:
            stale = [k for k, v in self._buckets.items()
                     if not v or v[-1] <= now - 3600]
            for k in stale:
                del self._buckets[k]
        return True


limiter = RateLimiter()


def client_ip() -> str:
    return request.remote_addr or "unknown"


# --------------------------------------------------------------- validators
def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) and len(email) <= 254


def parse_amount(raw, *, field, minimum=None, maximum=1e12,
                 allow_negative=False) -> float:
    try:
        value = float(str(raw).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number.")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be a number.")
    if not allow_negative and value < 0:
        raise ValueError(f"{field} can't be negative.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    if abs(value) > maximum:
        raise ValueError(f"{field} is unrealistically large.")
    return value


def parse_date(raw, *, field="Date") -> str:
    try:
        return datetime.strptime(str(raw).strip()[:10], "%Y-%m-%d") \
                       .strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{field} must be a valid date (YYYY-MM-DD).")


def clean_text(raw, *, field, max_len=120, required=False) -> str:
    value = (raw or "").strip()
    if required and not value:
        raise ValueError(f"{field} is required.")
    if len(value) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters.")
    return value


def require_choice(raw, choices, *, field) -> str:
    value = (raw or "").strip()
    if value not in choices:
        raise ValueError(f"{field} must be one of: {', '.join(choices)}.")
    return value


# ---------------------------------------------------------------- app hooks
def init_app(app):
    @app.before_request
    def load_user_and_guard():
        _load_current_user()
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            _check_same_origin()
            _check_csrf()
