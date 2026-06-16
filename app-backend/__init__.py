"""Cairn — application factory."""
import os
import secrets
import sys
from datetime import datetime

from flask import Flask, g, render_template, request, session


def _frozen() -> bool:
    return getattr(sys, "frozen", False)


def _resource_dir() -> str:
    """Where bundled templates/static live (PyInstaller unpack dir or pkg)."""
    if _frozen():
        return os.path.join(sys._MEIPASS, "app")  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def _writable_instance() -> str:
    """A writable folder for the DB + secret key.

    Frozen: a 'Cairn' folder next to the .exe (portable). Falls back
    to %LOCALAPPDATA% if the exe sits somewhere read-only.
    """
    if _frozen():
        exe_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(exe_dir, "Cairn-data")
        try:
            os.makedirs(candidate, exist_ok=True)
            test = os.path.join(candidate, ".write_test")
            with open(test, "w") as f:
                f.write("ok")
            os.remove(test)
            return candidate
        except OSError:
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            return os.path.join(base, "Cairn")
    return None  # non-frozen: Flask's default instance path is fine


def _load_secret_key(instance_path: str) -> str:
    """Persist a random secret key in the instance folder (created once)."""
    path = os.path.join(instance_path, "secret.key")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if len(key) >= 43:
                return key
    key = secrets.token_urlsafe(48)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


def create_app() -> Flask:
    res = _resource_dir()
    forced_instance = _writable_instance()
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=os.path.join(res, "templates"),
        static_folder=os.path.join(res, "static"),
        instance_path=forced_instance,  # None -> Flask default
    )
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.update(
        SECRET_KEY=_load_secret_key(app.instance_path),
        DATABASE=os.environ.get(
            "FINANCE_DB_PATH", os.path.join(app.instance_path, "finance.db")
        ),
        # Flask's signed cookie is used ONLY for CSRF + flash messages.
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FINANCE_HTTPS", "") == "1",
        MAX_CONTENT_LENGTH=1024 * 1024,  # 1 MB request cap
    )

    from . import db
    db.init_app(app)

    from . import security
    security.init_app(app)

    from .auth import bp as auth_bp
    from .portfolio import bp as portfolio_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(portfolio_bp)

    # ---------- template filters ----------
    @app.template_filter("money")
    def money(v, decimals=2):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "-"
        sign = "-" if v < 0 else ""
        return f"{sign}${abs(v):,.{decimals}f}"

    @app.template_filter("signed_money")
    def signed_money(v, decimals=2):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "-"
        sign = "+" if v > 0 else ("-" if v < 0 else "")
        return f"{sign}${abs(v):,.{decimals}f}"

    @app.template_filter("pct")
    def pct(v, decimals=1):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "-"
        return f"{v * 100:,.{decimals}f}%"

    @app.template_filter("signed_pct")
    def signed_pct(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "-"
        sign = "+" if v > 0 else ""
        return f"{sign}{v * 100:,.2f}%"

    @app.template_filter("qty")
    def qty(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "-"
        if v == int(v):
            return f"{int(v):,}"
        return f"{v:,.8f}".rstrip("0").rstrip(".")

    @app.template_filter("monthly")
    def monthly(amount, frequency):
        from .services.planning import to_monthly
        return to_monthly(amount, frequency)

    @app.template_filter("nicedate")
    def nicedate(v):
        try:
            return datetime.strptime(str(v)[:10], "%Y-%m-%d").strftime("%b %d, %Y")
        except ValueError:
            return str(v)

    # csrf_token is a Jinja global (not just a context var) so that macros
    # imported without `with context` can still call it.
    from .security import csrf_token
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def inject_globals():
        return {
            "current_user": getattr(g, "user", None),
            "now_year": datetime.now().year,
        }

    # ---------- security headers ----------
    @app.after_request
    def set_security_headers(resp):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
            "object-src 'none'"
        )
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        # Never cache: financial pages are sensitive, and for the local test
        # build this guarantees a relaunch always serves the current version
        # instead of a stale page from the browser cache.
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------- error pages ----------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               message="That page doesn't exist."), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403,
                               message="You don't have access to that."), 403

    @app.errorhandler(413)
    def too_large(e):
        return render_template("error.html", code=413,
                               message="Request too large."), 413

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500,
                               message="Something went wrong on our end."), 500

    return app
