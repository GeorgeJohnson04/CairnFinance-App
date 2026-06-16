<div align="center">

# 💜 Cairn

**Your one-stop shop for tracking savings, investments, dividends, and goals.**

A secure, multi-user personal-finance web app — an all-encompassing portfolio
tracker that replaces (and fixes) the classic finance spreadsheet.

</div>

---

> ⚠️ **No financial advice.** Cairn is a personal tracking and modeling tool
> only. It does **not** provide financial, investment, tax, or legal advice and
> makes no recommendation to buy or sell any security. Projections are
> hypothetical illustrations; market data may be delayed. All decisions are
> your own.

## ✨ Features

| | |
|---|---|
| 🔐 **Private accounts** | Each person signs up and sees **only their own data** — isolation is enforced at the database-query layer. |
| 📊 **Dashboard** | Total value, unrealized & realized P&L, total return, allocation by account / asset type / industry. |
| 📈 **Growth chart** | An area chart of cumulative money **earned or lost** (realized P&L + income) over time, plus a value-snapshot curve that builds going forward. |
| 🗂️ **All-asset portfolio** | Stocks, ETFs, mutual funds, crypto, **bonds**, options, **real estate**, **commodities**, cash, and anything else. |
| 🔎 **Live ticker search** | Type a symbol or company name → live results & current price from Yahoo Finance, fetched server-side. |
| 🧾 **Smart trade log** | Log a buy/sell and holdings + **average cost basis** + **realized P&L** update automatically. |
| 💎 **Income tracker** | Dividends & interest by type and account, with income YTD. |
| 🧭 **Financial plan** | Add your **job & expenses** → see surplus, savings rate, emergency-fund readiness, and a **model investing posture** (Aggressive → Capital Preservation) with a stock/bond/cash split and growth projections. |
| 🎯 **Savings & goals** | Progress bars for goals + Roth/IRA contribution tracking across all retirement accounts combined. |
| ⚡ **Live price refresh** | One click updates stock, ETF, mutual-fund, and crypto prices. |

## 🛡️ Security

Built for sensitive financial data:

- **Argon2id** password hashing (memory-hard, tuned parameters)
- **Database-backed, revocable sessions** — HttpOnly + SameSite cookies; only a
  SHA-256 hash of the session token is stored, so a leaked DB can't be replayed
- **CSRF tokens + same-origin checks** on every mutating request
- **Strict Content-Security-Policy** and a full set of security headers
  (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, …)
- **Rate limiting** on sign-in, registration, password change, price refresh,
  and market-data lookups
- **`no-store`** caching on authenticated pages
- Account-enumeration-resistant login (constant-time dummy verification)
- Per-user data isolation enforced in **every** query

## 🚀 Quick start (development)

```bash
pip install -r requirements.txt
python run.py
# open http://127.0.0.1:5000
```

> Python 3.10+ required.

## 🖥️ Run the desktop test build (.exe)

```bash
python build_exe.py
# then double-click dist/Cairn.exe
```

The `.exe` starts a local server, opens your browser, and stores its database
in a portable `Cairn-data` folder next to the executable.
**For local testing only** — it uses Flask's development server.

## 📥 Import the old Excel workbook

Bring in a `Finance Project.xlsx`, with its known spreadsheet errors corrected
on the way in:

```bash
python import_excel.py --file "path/to/Finance Project.xlsx" \
    --email you@example.com --create --name "Your Name"
```

**Corrections applied during import**

1. Account names trimmed (`"Fidelity "` → `"Fidelity"`) so totals never
   silently drop rows the way the spreadsheet's `SUMPRODUCT` did.
2. Asset types normalized (the trade log had `XLE` as *Stock*; it's an *ETF*).
3. Money-market trades with a missing price default to $1.00/share.
4. Realized P&L recomputed consistently for every sell.
5. **Every** account included in every breakdown — the Excel dashboard omitted
   *Robinhood Roth IRA* from its by-account and income summaries.
6. "Without retirement" totals derived from each account's type, fixing the
   `W/O ROTH` formula that excluded the Fidelity CMA.
7. Roth contributions and the annual limit become structured records instead of
   hardcoded cells.

## 🧮 How the planner works

The plan is an **illustrative model**, not advice. It:

- normalizes every income source & expense to a monthly figure;
- computes surplus, savings rate, and emergency-fund readiness
  (target = monthly expenses × your chosen number of months);
- derives a target equity weight from the classic *“120 − age”* rule of thumb,
  tilted by your self-reported risk tolerance (1–5);
- maps that to a posture label and a stocks / bonds / cash split;
- projects illustrative 10/20/30-year growth of the suggested monthly
  investment at a blended expected return.

## 🗂️ Project layout

```
run.py                 # dev entry point
launcher.py            # desktop/exe entry point (opens browser)
build_exe.py           # PyInstaller build script (builds in a temp dir)
import_excel.py        # one-time Excel importer (CLI)
tests/smoke_test.py    # end-to-end smoke test (Flask test client)
app/
  __init__.py          # app factory, security headers, template filters
  db.py                # SQLite schema + versioned migrations (every table has user_id)
  security.py          # Argon2, sessions, CSRF, rate limiting, validators
  auth.py              # register / login / logout
  portfolio.py         # all app pages + JSON market-data endpoints
  services/
    compute.py         # portfolio math: cost basis, P&L, aggregations, growth
    planning.py        # cashflow + model investing posture
    prices.py          # Yahoo/CoinGecko search, quotes, bulk refresh
    importer.py        # Excel import with the corrections above
  templates/  static/  # Jinja templates + white/purple design system
```

## 🧪 Tests

```bash
python tests/smoke_test.py
```

Covers registration, login, CSRF rejection, per-user data isolation,
cross-user access (404), holdings/trades/income/plan flows, the growth chart,
and security headers.

## 🛠️ Tech

Python · Flask · SQLite · Argon2id · vanilla JS (hand-rolled SVG charts, no
front-end framework) · Yahoo Finance & CoinGecko for market data.

## 📦 Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for publishing to a real domain (web),
hardening for production, and notes on the "app store" path.

## 📄 License

MIT — see [LICENSE](LICENSE).

<div align="center"><sub>Made with 💜 — not financial advice.</sub></div>
