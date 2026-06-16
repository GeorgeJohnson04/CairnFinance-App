"""Register / login / logout."""
import sqlite3

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)

from .db import get_db
from .security import (client_ip, end_session, equalize_timing, hash_password,
                       limiter, password_problems, safe_next, start_session,
                       valid_email, verify_password)

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.user:
        return redirect(url_for("portfolio.dashboard"))
    errors = []
    name = ""
    email = ""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        if not limiter.allow("register", client_ip(), limit=5,
                             per_seconds=3600):
            errors.append("Too many sign-up attempts. Try again later.")
        if not errors:
            if not name or len(name) > 80:
                errors.append("Please tell us your name (max 80 characters).")
            if not valid_email(email):
                errors.append("That email address doesn't look valid.")
            errors.extend(password_problems(password))
            if password != confirm:
                errors.append("Passwords don't match.")
            if not errors and password.lower().strip() == email:
                errors.append("Password can't be your email address.")

        if not errors:
            db = get_db()
            try:
                cur = db.execute(
                    "INSERT INTO users (email, name, pw_hash) VALUES (?, ?, ?)",
                    (email, name, hash_password(password)),
                )
                db.commit()
            except sqlite3.IntegrityError:
                # Same generic message as success path timing-wise is hard to
                # equalize perfectly; we at least avoid confirming the email.
                errors.append(
                    "Couldn't create the account. If you already have one, "
                    "try signing in instead.")
            else:
                user_id = cur.lastrowid
                resp = redirect(url_for("portfolio.dashboard"))
                flash(f"Welcome to Cairn, {name}! Start by adding an "
                      "account under Settings, or import your data.", "success")
                return start_session(resp, user_id)

    return render_template("auth/register.html", errors=errors,
                           name=name, email=email)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user:
        return redirect(url_for("portfolio.dashboard"))
    errors = []
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        ip = client_ip()
        if not limiter.allow("login-ip", ip, limit=20, per_seconds=900) or \
           not limiter.allow("login-email", f"{email}", limit=8,
                             per_seconds=900):
            errors.append("Too many sign-in attempts. "
                          "Please wait 15 minutes and try again.")
        else:
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE email = ?",
                              (email,)).fetchone()
            if user is None:
                equalize_timing(password)
                errors.append("Incorrect email or password.")
            elif not verify_password(user["pw_hash"], password):
                errors.append("Incorrect email or password.")
            else:
                resp = redirect(safe_next(request.args.get("next")))
                return start_session(resp, user["id"])

    return render_template("auth/login.html", errors=errors, email=email)


@bp.route("/logout", methods=("POST",))
def logout():
    resp = redirect(url_for("portfolio.landing"))
    flash("You've been signed out.", "success")
    return end_session(resp)
