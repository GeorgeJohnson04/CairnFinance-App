# Publishing Cairn

This guide covers getting Cairn onto a real domain that anyone can sign up to,
how to harden it for production, and the realistic story on "the app store."

> **TL;DR:** Cairn is a **web app**, so you publish it to a **web host with a
> custom domain** (not an app store). You *can* later wrap it as a mobile/
> desktop app, but start with the website.

---

## 1. Web vs. "app store" — which path is this?

| | What it is | How you publish |
|---|---|---|
| **Web app (this project)** | Runs on a server; users visit a URL in any browser. | Deploy to a host, point a domain at it. **← start here** |
| **Mobile app (iOS/Android)** | Native app installed from the App Store / Google Play. | Requires wrapping the web app (or rebuilding) — see §6. |
| **Desktop app** | The `.exe` you already have. | Distribute the file directly. Already done for testing. |

Cairn is a Flask web app, so the primary path is **§2–§5 (web)**. The
"app store" is a separate, later step (§6).

---

## 2. Get production-ready first

The dev server (`python run.py`) and the `.exe` are **not** for public traffic.
Before going live:

1. **Use a production WSGI server.** Add **gunicorn** (Linux) or **waitress**
   (cross-platform) instead of Flask's built-in server.
   ```bash
   pip install waitress
   # serve the app factory:
   waitress-serve --host 0.0.0.0 --port 8000 --call app:create_app
   ```
2. **Put HTTPS in front.** Set the env var `FINANCE_HTTPS=1` so session cookies
   are marked `Secure`. Terminate TLS at a reverse proxy (Caddy/Nginx) or let
   the host do it (most PaaS providers give you HTTPS automatically).
3. **Persist the data + secret key.** The SQLite DB and `secret.key` live in the
   `instance/` folder. Point `FINANCE_DB_PATH` at a **persistent disk** (not an
   ephemeral container filesystem), and back it up.
4. **Set env vars:** `FINANCE_HTTPS=1`, `FINANCE_DB_PATH=/data/finance.db`.
   Never enable `FINANCE_DEBUG`.

A ready-to-use `Procfile`-style start command:

```
web: waitress-serve --port=$PORT --call app:create_app
```

---

## 3. Pick a host (easiest → most control)

| Host | Good for | Notes |
|---|---|---|
| **Render.com** | Easiest Flask deploy | Free tier, auto-HTTPS, persistent disk add-on. Point it at your GitHub repo; start command above. |
| **Railway.app** | Fast Git deploys | Similar to Render; add a volume for the DB. |
| **Fly.io** | Global, cheap | Needs a `fly.toml` + a mounted volume for SQLite. |
| **PythonAnywhere** | Beginner-friendly | Simple Flask hosting with a WSGI config. |
| **A VPS** (DigitalOcean, Hetzner, Lightsail) | Full control | You install Python + Caddy/Nginx yourself. Most work, most flexibility. |

**Recommended for you: Render.** Connect the GitHub repo (see §7), set the
start command and env vars, attach a persistent disk mounted at `/data`, done.

> Since the database is single-file SQLite, **always attach a persistent
> volume** — otherwise a redeploy wipes user data. For many concurrent users
> you'd later migrate to Postgres, but SQLite is fine to launch.

---

## 4. Get a domain

1. **Buy a domain** from a registrar — Namecheap, Cloudflare Registrar
   (at-cost pricing), Porkbun, or Google Domains successor (Squarespace).
   Something like `cairnfinance.app` or `getcairn.io`.
2. **Point it at your host:**
   - On the host, add your custom domain in its dashboard (e.g. Render →
     *Settings → Custom Domain*).
   - At the registrar, add the DNS record the host gives you — usually a
     `CNAME` for `www` → your host, and an `A`/`ALIAS` for the apex (`@`).
3. **HTTPS** is then issued automatically (Let's Encrypt) by Render/Railway/Fly/
   Caddy. Verify the padlock shows and set `FINANCE_HTTPS=1`.

DNS changes can take a few minutes to a few hours to propagate.

---

## 5. Pre-launch checklist

- [ ] Running under waitress/gunicorn, **not** the dev server
- [ ] `FINANCE_HTTPS=1` and HTTPS verified (padlock)
- [ ] `FINANCE_DB_PATH` on a **persistent, backed-up** disk
- [ ] `FINANCE_DEBUG` unset
- [ ] Custom domain resolves and redirects http→https
- [ ] You've reviewed the "No financial advice" disclaimer wording
- [ ] (Recommended) A privacy policy + terms page, since you store personal
      financial data — and a real backup schedule

---

## 6. Later: the mobile "app store" path

Once the website is live, you have three options to get into app stores:

1. **PWA (cheapest, no store needed).** Add a web-app manifest + service worker
   so users can "Install" Cairn to their home screen straight from the
   browser. No store fees, no review. Good first step.
2. **Wrap the website** with **Capacitor** or **Tauri** (mobile) — these load
   your web UI in a native shell you can submit to the App Store / Google Play.
   You'll need an **Apple Developer account ($99/yr)** and a **Google Play
   account ($25 one-time)**, plus you must pass each store's review.
3. **Rebuild natively** (React Native / Flutter) talking to Cairn's JSON
   endpoints. Most effort; best native feel.

Either way the server from §2–§5 stays the backend; the app just talks to it.

---

## 7. Push to GitHub

```bash
cd "Finance App"
git init
git add .
git commit -m "Cairn: secure multi-user portfolio tracker"
git branch -M main
git remote add origin https://github.com/<you>/cairn-finance.git
git push -u origin main
```

The included `.gitignore` already excludes `instance/`, `dist/`, build
artifacts, `__pycache__/`, and `*.db` — so **no secrets or user data** get
committed. Double-check `git status` before your first push.
