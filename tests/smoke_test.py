"""End-to-end smoke test using Flask's test client."""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["FINANCE_DB_PATH"] = os.path.join(tempfile.gettempdir(),
                                             "cairn_smoke.db")
if os.path.exists(os.environ["FINANCE_DB_PATH"]):
    os.remove(os.environ["FINANCE_DB_PATH"])

from app import create_app

app = create_app()
c = app.test_client()


def csrf(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def check(label, cond):
    print(("  OK  " if cond else " FAIL ") + label)
    assert cond, label


# landing
r = c.get("/")
check("landing 200", r.status_code == 200)
check("landing mentions Cairn", b"Cairn" in r.data)

# register page has the disclaimer
r = c.get("/register")
check("register page 200", r.status_code == 200)
check("register has 'No financial advice'", b"No financial advice" in r.data)
token = csrf(r.get_data(as_text=True))

# register a user
r = c.post("/register", data={
    "csrf_token": token, "name": "Test User",
    "email": "test@example.com", "password": "violet-otter-42",
    "confirm": "violet-otter-42",
}, follow_redirects=True)
check("register -> dashboard", b"Welcome back" in r.data or b"money HQ" in r.data)

# dashboard loads
r = c.get("/dashboard")
check("dashboard 200", r.status_code == 200)

# add an account
r = c.get("/settings")
token = csrf(r.get_data(as_text=True))
r = c.post("/settings/accounts/add", data={
    "csrf_token": token, "name": "Fidelity", "kind": "brokerage",
}, follow_redirects=True)
check("account added", b"Fidelity" in r.data)

# get account id
with app.app_context():
    from app.db import get_db
    acc = get_db().execute("SELECT id FROM accounts WHERE name='Fidelity'").fetchone()
acct_id = acc["id"]

# add a holding
r = c.get("/holdings")
token = csrf(r.get_data(as_text=True))
r = c.post("/holdings/add", data={
    "csrf_token": token, "account_id": acct_id, "asset_type": "Stock",
    "ticker": "AAPL", "name": "Apple", "industry": "Technology",
    "quantity": "10", "avg_cost": "150", "current_price": "200",
}, follow_redirects=True)
check("holding AAPL added", b"AAPL" in r.data)
check("market value shows", b"2,000" in r.data)

# log a trade (sell) -> realized P&L computed
r = c.get("/trades")
token = csrf(r.get_data(as_text=True))
r = c.post("/trades/add", data={
    "csrf_token": token, "account_id": acct_id, "asset_type": "Stock",
    "ticker": "AAPL", "action": "Sell", "quantity": "5", "price": "210",
    "trade_date": "2026-06-01", "note": "",
}, follow_redirects=True)
check("sell logged with realized P&L", b"realized" in r.data.lower())

# add an earlier-dated dividend so the growth series spans multiple months
r = c.get("/income")
token = csrf(r.get_data(as_text=True))
c.post("/income/add", data={
    "csrf_token": token, "account_id": acct_id, "type": "Qualified Dividend",
    "income_date": "2026-04-15", "ticker": "AAPL", "amount": "12.50",
    "description": "Q1 dividend",
}, follow_redirects=True)

# add a non-equity asset (bond) — proves broadened asset types work
r = c.get("/holdings")
token = csrf(r.get_data(as_text=True))
r = c.post("/holdings/add", data={
    "csrf_token": token, "account_id": acct_id, "asset_type": "Bond",
    "ticker": "UST10Y", "name": "US Treasury 10Y", "industry": "Government",
    "quantity": "1", "avg_cost": "1000", "current_price": "1020",
}, follow_redirects=True)
check("bond holding added (all-asset)", b"UST10Y" in r.data)

# plan page + income/expense + recommendation
r = c.get("/plan")
check("plan page 200", r.status_code == 200)
token = csrf(r.get_data(as_text=True))
c.post("/plan/income/add", data={"csrf_token": token, "name": "Job",
        "kind": "salary", "amount": "6000", "frequency": "monthly",
        "is_gross": "1"}, follow_redirects=True)
token = csrf(c.get("/plan").get_data(as_text=True))
c.post("/plan/expense/add", data={"csrf_token": token, "name": "Rent",
        "category": "Housing", "amount": "2000", "frequency": "monthly"},
       follow_redirects=True)
r = c.get("/plan")
check("plan shows surplus", b"4,000" in r.data)
check("plan shows a model strategy",
      b"Model strategy" in r.data and (b"Growth" in r.data or
      b"Balanced" in r.data or b"Aggressive" in r.data))

# growth series present on dashboard (we logged a sell earlier)
r = c.get("/dashboard")
check("dashboard growth chart present", b'data-linechart="growth"' in r.data)

# CSRF rejection
r = c.post("/holdings/add", data={"account_id": acct_id, "ticker": "X"})
check("missing CSRF -> 403", r.status_code == 403)

# data isolation: second user can't see first user's holdings
r = c.post("/logout", data={"csrf_token": csrf(c.get('/dashboard').get_data(as_text=True))})
r = c.get("/register")
token = csrf(r.get_data(as_text=True))
c.post("/register", data={
    "csrf_token": token, "name": "Mallory", "email": "m@example.com",
    "password": "second-user-99", "confirm": "second-user-99",
}, follow_redirects=True)
# Mallory has no accounts: she must see the empty state, never user 1's
# Apple position (market value 2,000 / cost basis). "AAPL" alone is not a
# valid probe — it appears in the add-holding search placeholder.
r = c.get("/holdings")
check("2nd user sees no leaked holding value (isolation)",
      b"2,000" not in r.data and b"Apple" not in r.data)
check("2nd user gets empty/onboarding state",
      b"Add an account first" in r.data or b"No holdings yet" in r.data)

# 2nd user editing 1st user's holding -> 404
with app.app_context():
    from app.db import get_db
    h = get_db().execute("SELECT id FROM holdings WHERE ticker='AAPL'").fetchone()
r = c.get("/holdings")
token = csrf(r.get_data(as_text=True))
r = c.post(f"/holdings/{h['id']}/delete", data={"csrf_token": token})
check("cross-user delete -> 404", r.status_code == 404)

# login required
c.post("/logout", data={"csrf_token": csrf(c.get('/dashboard').get_data(as_text=True))})
r = c.get("/dashboard")
check("dashboard redirects when logged out", r.status_code == 302)

# security headers
r = c.get("/login")
check("CSP header present", "Content-Security-Policy" in r.headers)
check("X-Frame-Options DENY", r.headers.get("X-Frame-Options") == "DENY")

print("\nAll smoke tests passed.")
