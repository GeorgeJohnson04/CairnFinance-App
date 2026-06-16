"""All authenticated app pages + the public landing page."""
from datetime import date

from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from .db import ASSET_TYPES, FREQUENCIES, get_db
from .security import (clean_text, client_ip, hash_password, limiter,
                       login_required, parse_amount, parse_date,
                       password_problems, require_choice,
                       revoke_other_sessions, verify_password)
from .services import compute, planning, prices

bp = Blueprint("portfolio", __name__)

INCOME_TYPES = ("Interest", "Qualified Dividend", "Ordinary Dividend", "Other")
ACCOUNT_KINDS = ("brokerage", "retirement", "cash", "savings", "other")


# ------------------------------------------------------------------ helpers
def _accounts(db):
    return db.execute(
        "SELECT * FROM accounts WHERE user_id = ? ORDER BY name",
        (g.user["id"],),
    ).fetchall()


def _own_account_or_404(db, account_id):
    row = db.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, g.user["id"]),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _flash_errors(errors):
    for e in errors:
        flash(e, "error")


# ------------------------------------------------------------------ landing
@bp.route("/")
def landing():
    if g.user:
        return redirect(url_for("portfolio.dashboard"))
    return render_template("landing.html")


# ---------------------------------------------------------------- dashboard
@bp.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    scope = request.args.get("scope", "all")
    include_retirement = scope != "ex-retirement"
    year = date.today().year

    summary = compute.portfolio_summary(db, g.user["id"], include_retirement)
    stats = compute.trade_stats(db, g.user["id"], year)
    income = compute.income_summary(db, g.user["id"], year)
    roth = compute.retirement_progress(db, g.user, year)

    active = [h for h in summary["holdings"] if (h["quantity"] or 0) > 0
              and h["asset_type"] != "Cash"]
    movers = sorted(active, key=lambda h: h["gl_pct"], reverse=True)
    total_return = (summary["unrealized"] + stats["realized"]
                    + income["total"])

    growth = compute.growth_series(db, g.user["id"])
    # opportunistically record today's value so the equity curve builds up
    try:
        compute.record_snapshot(db, g.user["id"])
    except Exception:
        pass

    return render_template(
        "app/dashboard.html",
        summary=summary, stats=stats, income=income, roth=roth,
        gainers=movers[:4], losers=list(reversed(movers[-4:])),
        total_return=total_return, scope=scope, year=year, growth=growth,
        has_accounts=bool(_accounts(db)),
    )


@bp.route("/refresh-prices", methods=("POST",))
@login_required
def refresh_prices():
    if not limiter.allow("refresh", str(g.user["id"]), limit=10,
                         per_seconds=3600):
        flash("Price refresh is limited to 10 per hour.", "error")
        return redirect(request.form.get("back") or
                        url_for("portfolio.dashboard"))
    db = get_db()
    updated, skipped = prices.refresh_user_prices(db, g.user["id"])
    if updated:
        flash(f"Updated live prices for {updated} holding"
              f"{'s' if updated != 1 else ''}.", "success")
    if skipped:
        flash("No quote found for: " + ", ".join(skipped[:10]), "error")
    if not updated and not skipped:
        flash("Nothing to refresh yet. Add some holdings first.", "error")
    back = request.form.get("back") or url_for("portfolio.dashboard")
    if not back.startswith("/") or back.startswith("//"):
        back = url_for("portfolio.dashboard")
    return redirect(back)


# ------------------------------------------------- live market data (JSON)
@bp.route("/api/search")
@login_required
def api_search():
    if not limiter.allow("search", str(g.user["id"]), limit=60,
                         per_seconds=60):
        return jsonify({"results": [], "error": "rate_limited"}), 429
    query = (request.args.get("q") or "").strip()[:40]
    if not query:
        return jsonify({"results": []})
    return jsonify({"results": prices.search_symbols(query)})


@bp.route("/api/quote")
@login_required
def api_quote():
    if not limiter.allow("quote", str(g.user["id"]), limit=120,
                         per_seconds=60):
        return jsonify({"error": "rate_limited"}), 429
    symbol = (request.args.get("symbol") or "").strip()[:20]
    quote = prices.get_quote(symbol)
    if quote is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(quote)


# ----------------------------------------------------------------- holdings
@bp.route("/holdings")
@login_required
def holdings():
    db = get_db()
    summary = compute.portfolio_summary(db, g.user["id"], True)
    return render_template("app/holdings.html", summary=summary,
                           accounts=_accounts(db), asset_types=ASSET_TYPES)


def _holding_form(db):
    account = _own_account_or_404(db, request.form.get("account_id", ""))
    asset_type = require_choice(request.form.get("asset_type"), ASSET_TYPES,
                                field="Asset type")
    ticker = clean_text(request.form.get("ticker"), field="Ticker",
                        max_len=20, required=True).upper()
    name = clean_text(request.form.get("name"), field="Name", max_len=80)
    industry = clean_text(request.form.get("industry"), field="Industry",
                          max_len=60)
    quantity = parse_amount(request.form.get("quantity"), field="Quantity")
    avg_cost = parse_amount(request.form.get("avg_cost"), field="Avg cost")
    price = parse_amount(request.form.get("current_price"),
                         field="Current price")
    return account, asset_type, ticker, name or ticker, industry, \
        quantity, avg_cost, price


@bp.route("/holdings/add", methods=("POST",))
@login_required
def holdings_add():
    db = get_db()
    try:
        (account, asset_type, ticker, name, industry, quantity, avg_cost,
         price) = _holding_form(db)
        existing = db.execute(
            "SELECT id FROM holdings WHERE user_id = ? AND account_id = ?"
            " AND ticker = ? AND asset_type = ?",
            (g.user["id"], account["id"], ticker, asset_type),
        ).fetchone()
        if existing:
            raise ValueError(
                f"{ticker} already exists in {account['name']}. "
                "Edit it instead.")
        db.execute(
            "INSERT INTO holdings (user_id, account_id, asset_type, ticker,"
            " name, industry, quantity, avg_cost, current_price,"
            " price_updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " datetime('now'))",
            (g.user["id"], account["id"], asset_type, ticker, name, industry,
             quantity, avg_cost, price),
        )
        db.commit()
        flash(f"Added {ticker} to {account['name']}.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.holdings"))


@bp.route("/holdings/<int:holding_id>/edit", methods=("POST",))
@login_required
def holdings_edit(holding_id):
    db = get_db()
    row = db.execute("SELECT * FROM holdings WHERE id = ? AND user_id = ?",
                     (holding_id, g.user["id"])).fetchone()
    if row is None:
        abort(404)
    try:
        (account, asset_type, ticker, name, industry, quantity, avg_cost,
         price) = _holding_form(db)
        db.execute(
            "UPDATE holdings SET account_id = ?, asset_type = ?, ticker = ?,"
            " name = ?, industry = ?, quantity = ?, avg_cost = ?,"
            " current_price = ?, price_updated_at = datetime('now')"
            " WHERE id = ? AND user_id = ?",
            (account["id"], asset_type, ticker, name, industry, quantity,
             avg_cost, price, holding_id, g.user["id"]),
        )
        db.commit()
        flash(f"Updated {ticker}.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.holdings"))


@bp.route("/holdings/<int:holding_id>/delete", methods=("POST",))
@login_required
def holdings_delete(holding_id):
    db = get_db()
    cur = db.execute("DELETE FROM holdings WHERE id = ? AND user_id = ?",
                     (holding_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Holding removed.", "success")
    return redirect(url_for("portfolio.holdings"))


# ------------------------------------------------------------------- trades
@bp.route("/trades")
@login_required
def trades():
    db = get_db()
    rows = db.execute(
        "SELECT t.*, a.name AS account_name FROM trades t"
        " JOIN accounts a ON a.id = t.account_id"
        " WHERE t.user_id = ? ORDER BY t.trade_date DESC, t.id DESC"
        " LIMIT 500",
        (g.user["id"],),
    ).fetchall()
    year = date.today().year
    stats_ytd = compute.trade_stats(db, g.user["id"], year)
    stats_all = compute.trade_stats(db, g.user["id"], None)
    return render_template("app/trades.html", trades=rows,
                           stats_ytd=stats_ytd, stats_all=stats_all,
                           year=year, accounts=_accounts(db),
                           asset_types=ASSET_TYPES)


@bp.route("/trades/add", methods=("POST",))
@login_required
def trades_add():
    db = get_db()
    try:
        account = _own_account_or_404(db, request.form.get("account_id", ""))
        trade_date = parse_date(request.form.get("trade_date"))
        asset_type = require_choice(request.form.get("asset_type"),
                                    ASSET_TYPES, field="Asset type")
        ticker = clean_text(request.form.get("ticker"), field="Ticker",
                            max_len=20, required=True).upper()
        action = require_choice(request.form.get("action"), ("Buy", "Sell"),
                                field="Action")
        quantity = parse_amount(request.form.get("quantity"),
                                field="Quantity", minimum=1e-12)
        price = parse_amount(request.form.get("price"), field="Price")
        note = clean_text(request.form.get("note"), field="Note", max_len=200)

        realized = compute.apply_trade(
            db, g.user["id"], account_id=account["id"], trade_date=trade_date,
            asset_type=asset_type, ticker=ticker, action=action,
            quantity=quantity, price=price, note=note)
        if realized is None:
            flash(f"Logged buy: {quantity:g} {ticker}. "
                  "Your holding and cost basis updated automatically.",
                  "success")
        else:
            word = "profit" if realized >= 0 else "loss"
            flash(f"Logged sell: {quantity:g} {ticker}, realized "
                  f"{word} of ${abs(realized):,.2f} (computed from your "
                  "average cost).", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.trades"))


@bp.route("/trades/<int:trade_id>/delete", methods=("POST",))
@login_required
def trades_delete(trade_id):
    db = get_db()
    cur = db.execute("DELETE FROM trades WHERE id = ? AND user_id = ?",
                     (trade_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Trade removed from the log. (Holdings are not rewound "
          "automatically. Adjust the holding if needed.)", "success")
    return redirect(url_for("portfolio.trades"))


# ------------------------------------------------------------------- income
@bp.route("/income")
@login_required
def income():
    db = get_db()
    rows = db.execute(
        "SELECT i.*, a.name AS account_name FROM incomes i"
        " JOIN accounts a ON a.id = i.account_id"
        " WHERE i.user_id = ? ORDER BY i.income_date DESC, i.id DESC"
        " LIMIT 500",
        (g.user["id"],),
    ).fetchall()
    year = date.today().year
    summary_ytd = compute.income_summary(db, g.user["id"], year)
    summary_all = compute.income_summary(db, g.user["id"], None)
    monthly = compute.monthly_income_series(db, g.user["id"], year)

    # Combined view: surface recurring income (salary & co., managed on the
    # Plan page) alongside investment payouts so all income lives in one place.
    cash = planning.cashflow(db, g.user["id"])
    mix = {}
    for s in cash["incomes"]:  # recurring sources at annual run-rate
        label = s["kind"].title()
        mix[label] = mix.get(label, 0.0) + planning.to_monthly(
            s["amount"], s["frequency"]) * 12
    div = sum(r["value"] for r in summary_ytd["by_type"]
              if "Dividend" in r["label"])
    interest = sum(r["value"] for r in summary_ytd["by_type"]
                   if r["label"] == "Interest")
    other_inv = sum(r["value"] for r in summary_ytd["by_type"]
                    if r["label"] == "Other")
    for lbl, val in (("Dividends", div), ("Interest", interest),
                     ("Other payouts", other_inv)):
        if val:
            mix[lbl] = mix.get(lbl, 0.0) + val
    income_mix = sorted(
        [{"label": k, "value": round(v, 2)} for k, v in mix.items() if v > 0],
        key=lambda x: -x["value"])

    return render_template("app/income.html", incomes=rows,
                           summary_ytd=summary_ytd, summary_all=summary_all,
                           monthly=monthly, year=year, accounts=_accounts(db),
                           income_types=INCOME_TYPES,
                           income_sources=cash["incomes"],
                           recurring_annual=cash["annual_income"],
                           recurring_monthly=cash["monthly_income"],
                           income_mix=income_mix)


@bp.route("/income/add", methods=("POST",))
@login_required
def income_add():
    db = get_db()
    try:
        account = _own_account_or_404(db, request.form.get("account_id", ""))
        income_date = parse_date(request.form.get("income_date"))
        income_type = require_choice(request.form.get("type"), INCOME_TYPES,
                                     field="Type")
        ticker = clean_text(request.form.get("ticker"), field="Ticker",
                            max_len=20).upper()
        description = clean_text(request.form.get("description"),
                                 field="Description", max_len=200)
        amount = parse_amount(request.form.get("amount"), field="Amount",
                              minimum=0.000001)
        db.execute(
            "INSERT INTO incomes (user_id, account_id, income_date, ticker,"
            " type, description, amount) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (g.user["id"], account["id"], income_date, ticker, income_type,
             description, amount),
        )
        db.commit()
        flash(f"Recorded ${amount:,.2f} of {income_type.lower()}.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.income"))


@bp.route("/income/<int:income_id>/delete", methods=("POST",))
@login_required
def income_delete(income_id):
    db = get_db()
    cur = db.execute("DELETE FROM incomes WHERE id = ? AND user_id = ?",
                     (income_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Income entry removed.", "success")
    return redirect(url_for("portfolio.income"))


# ------------------------------------------------------------------ savings
@bp.route("/savings")
@login_required
def savings():
    db = get_db()
    goals = db.execute(
        "SELECT * FROM goals WHERE user_id = ? ORDER BY created_at",
        (g.user["id"],),
    ).fetchall()
    summary = compute.portfolio_summary(db, g.user["id"], True)
    cash_holdings = [h for h in summary["all_holdings"]
                     if h["asset_type"] == "Cash" and (h["quantity"] or 0) > 0]
    cash_total = sum(h["market_value"] for h in cash_holdings)
    year = date.today().year
    roth = compute.retirement_progress(db, g.user, year)
    contributions = db.execute(
        "SELECT c.*, a.name AS account_name FROM contributions c"
        " JOIN accounts a ON a.id = c.account_id"
        " WHERE c.user_id = ? ORDER BY c.contrib_date DESC LIMIT 100",
        (g.user["id"],),
    ).fetchall()
    retirement_accounts = [a for a in _accounts(db)
                           if a["kind"] == "retirement"]
    contrib_series = compute.contributions_series(db, g.user["id"], year)
    goals_saved = [{"label": gl["name"], "value": gl["saved_amount"]}
                   for gl in goals if (gl["saved_amount"] or 0) > 0]
    return render_template("app/savings.html", goals=goals,
                           cash_holdings=cash_holdings, cash_total=cash_total,
                           roth=roth, contributions=contributions,
                           contrib_series=contrib_series, goals_saved=goals_saved,
                           retirement_accounts=retirement_accounts, year=year)


@bp.route("/goals/add", methods=("POST",))
@login_required
def goals_add():
    db = get_db()
    try:
        name = clean_text(request.form.get("name"), field="Goal name",
                          max_len=80, required=True)
        target = parse_amount(request.form.get("target_amount"),
                              field="Target amount", minimum=0.01)
        saved = parse_amount(request.form.get("saved_amount") or "0",
                             field="Saved so far")
        target_date = (request.form.get("target_date") or "").strip()
        target_date = parse_date(target_date) if target_date else None
        db.execute(
            "INSERT INTO goals (user_id, name, target_amount, saved_amount,"
            " target_date) VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], name, target, saved, target_date),
        )
        db.commit()
        flash(f'Goal "{name}" created.', "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.savings"))


@bp.route("/goals/<int:goal_id>/edit", methods=("POST",))
@login_required
def goals_edit(goal_id):
    db = get_db()
    row = db.execute("SELECT * FROM goals WHERE id = ? AND user_id = ?",
                     (goal_id, g.user["id"])).fetchone()
    if row is None:
        abort(404)
    try:
        name = clean_text(request.form.get("name"), field="Goal name",
                          max_len=80, required=True)
        target = parse_amount(request.form.get("target_amount"),
                              field="Target amount", minimum=0.01)
        saved = parse_amount(request.form.get("saved_amount") or "0",
                             field="Saved so far")
        target_date = (request.form.get("target_date") or "").strip()
        target_date = parse_date(target_date) if target_date else None
        db.execute(
            "UPDATE goals SET name = ?, target_amount = ?, saved_amount = ?,"
            " target_date = ? WHERE id = ? AND user_id = ?",
            (name, target, saved, target_date, goal_id, g.user["id"]),
        )
        db.commit()
        flash(f'Goal "{name}" updated.', "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.savings"))


@bp.route("/goals/<int:goal_id>/delete", methods=("POST",))
@login_required
def goals_delete(goal_id):
    db = get_db()
    cur = db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?",
                     (goal_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Goal deleted.", "success")
    return redirect(url_for("portfolio.savings"))


@bp.route("/contributions/add", methods=("POST",))
@login_required
def contributions_add():
    db = get_db()
    try:
        account = _own_account_or_404(db, request.form.get("account_id", ""))
        if account["kind"] != "retirement":
            raise ValueError("Contributions are tracked for retirement "
                             "accounts only.")
        contrib_date = parse_date(request.form.get("contrib_date"))
        amount = parse_amount(request.form.get("amount"), field="Amount",
                              minimum=0.01)
        note = clean_text(request.form.get("note"), field="Note", max_len=200)
        db.execute(
            "INSERT INTO contributions (user_id, account_id, year, amount,"
            " contrib_date, note) VALUES (?, ?, ?, ?, ?, ?)",
            (g.user["id"], account["id"], int(contrib_date[:4]), amount,
             contrib_date, note),
        )
        db.commit()
        flash(f"Contribution of ${amount:,.2f} recorded.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.savings"))


@bp.route("/contributions/<int:contrib_id>/delete", methods=("POST",))
@login_required
def contributions_delete(contrib_id):
    db = get_db()
    cur = db.execute("DELETE FROM contributions WHERE id = ? AND user_id = ?",
                     (contrib_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Contribution removed.", "success")
    return redirect(url_for("portfolio.savings"))


# -------------------------------------------------------------------- plan
@bp.route("/plan")
@login_required
def plan():
    db = get_db()
    cash = planning.cashflow(db, g.user["id"])
    summary = compute.portfolio_summary(db, g.user["id"], True)
    # liquid savings = cash holdings + balances in cash/savings accounts
    liquid = sum(h["market_value"] for h in summary["all_holdings"]
                 if h["asset_type"] == "Cash"
                 or h["account_kind"] in ("cash", "savings"))
    rec = planning.recommendation(db, g.user, cash, liquid)
    flow = planning.spending_flow(cash)
    return render_template("app/plan.html", cash=cash, rec=rec, flow=flow,
                           frequencies=FREQUENCIES,
                           categories=planning.EXPENSE_CATEGORIES,
                           income_kinds=planning.INCOME_KINDS)


@bp.route("/plan/income/add", methods=("POST",))
@login_required
def income_source_add():
    db = get_db()
    try:
        name = clean_text(request.form.get("name"), field="Source name",
                          max_len=80, required=True)
        kind = require_choice(request.form.get("kind"),
                              planning.INCOME_KINDS, field="Type")
        amount = parse_amount(request.form.get("amount"), field="Amount",
                              minimum=0.01)
        frequency = require_choice(request.form.get("frequency"), FREQUENCIES,
                                   field="Frequency")
        is_gross = 1 if request.form.get("is_gross") == "1" else 0
        db.execute(
            "INSERT INTO income_sources (user_id, name, kind, amount,"
            " frequency, is_gross) VALUES (?, ?, ?, ?, ?, ?)",
            (g.user["id"], name, kind, amount, frequency, is_gross))
        db.commit()
        flash(f'Added income source "{name}".', "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.plan"))


@bp.route("/plan/income/<int:source_id>/delete", methods=("POST",))
@login_required
def income_source_delete(source_id):
    db = get_db()
    cur = db.execute("DELETE FROM income_sources WHERE id = ? AND user_id = ?",
                     (source_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Income source removed.", "success")
    return redirect(url_for("portfolio.plan"))


@bp.route("/plan/expense/add", methods=("POST",))
@login_required
def expense_add():
    db = get_db()
    try:
        name = clean_text(request.form.get("name"), field="Expense name",
                          max_len=80, required=True)
        category = require_choice(request.form.get("category"),
                                  planning.EXPENSE_CATEGORIES, field="Category")
        amount = parse_amount(request.form.get("amount"), field="Amount",
                              minimum=0.01)
        frequency = require_choice(request.form.get("frequency"), FREQUENCIES,
                                   field="Frequency")
        db.execute(
            "INSERT INTO expenses (user_id, name, category, amount, frequency)"
            " VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], name, category, amount, frequency))
        db.commit()
        flash(f'Added expense "{name}".', "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.plan"))


@bp.route("/plan/expense/<int:expense_id>/delete", methods=("POST",))
@login_required
def expense_delete(expense_id):
    db = get_db()
    cur = db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?",
                     (expense_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Expense removed.", "success")
    return redirect(url_for("portfolio.plan"))


@bp.route("/plan/profile", methods=("POST",))
@login_required
def plan_profile():
    db = get_db()
    try:
        risk = require_choice(request.form.get("risk_tolerance"),
                              ("1", "2", "3", "4", "5"), field="Risk tolerance")
        emergency = parse_amount(request.form.get("emergency_months") or "6",
                                 field="Emergency months", minimum=0,
                                 maximum=60)
        birth_raw = (request.form.get("birth_year") or "").strip()
        birth_year = None
        if birth_raw:
            by = int(parse_amount(birth_raw, field="Birth year",
                                  minimum=1900, maximum=date.today().year))
            birth_year = by
        employment = clean_text(request.form.get("employment"),
                                field="Employment", max_len=60)
        db.execute(
            "UPDATE users SET risk_tolerance = ?, emergency_months = ?,"
            " birth_year = ?, employment = ? WHERE id = ?",
            (int(risk), emergency, birth_year, employment, g.user["id"]))
        db.commit()
        flash("Plan profile updated.", "success")
    except (ValueError, TypeError) as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.plan"))


# ----------------------------------------------------------------- settings
@bp.route("/settings")
@login_required
def settings():
    db = get_db()
    sessions = db.execute(
        "SELECT id, created_at, last_seen, user_agent FROM sessions"
        " WHERE user_id = ? ORDER BY last_seen DESC",
        (g.user["id"],),
    ).fetchall()
    counts = db.execute(
        "SELECT (SELECT COUNT(*) FROM holdings WHERE user_id = :u) AS holdings,"
        " (SELECT COUNT(*) FROM trades WHERE user_id = :u) AS trades,"
        " (SELECT COUNT(*) FROM incomes WHERE user_id = :u) AS incomes",
        {"u": g.user["id"]},
    ).fetchone()
    return render_template("app/settings.html", accounts=_accounts(db),
                           sessions=sessions, account_kinds=ACCOUNT_KINDS,
                           counts=counts)


@bp.route("/settings/profile", methods=("POST",))
@login_required
def settings_profile():
    db = get_db()
    try:
        name = clean_text(request.form.get("name"), field="Name",
                          max_len=80, required=True)
        db.execute("UPDATE users SET name = ? WHERE id = ?",
                   (name, g.user["id"]))
        db.commit()
        flash("Profile updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.settings"))


@bp.route("/settings/password", methods=("POST",))
@login_required
def settings_password():
    db = get_db()
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not limiter.allow("pwchange", str(g.user["id"]), limit=5,
                         per_seconds=900):
        flash("Too many attempts. Wait 15 minutes.", "error")
        return redirect(url_for("portfolio.settings"))

    errors = []
    if not verify_password(g.user["pw_hash"], current):
        errors.append("Your current password is incorrect.")
    errors.extend(password_problems(new))
    if new != confirm:
        errors.append("New passwords don't match.")
    if errors:
        _flash_errors(errors)
        return redirect(url_for("portfolio.settings"))

    db.execute("UPDATE users SET pw_hash = ? WHERE id = ?",
               (hash_password(new), g.user["id"]))
    db.commit()
    revoke_other_sessions(g.user["id"], g.session_id)
    flash("Password changed. All other sessions were signed out.", "success")
    return redirect(url_for("portfolio.settings"))


@bp.route("/settings/ira-limit", methods=("POST",))
@login_required
def settings_ira_limit():
    db = get_db()
    try:
        limit = parse_amount(request.form.get("ira_limit"),
                             field="Contribution limit", minimum=0,
                             maximum=1e6)
        db.execute("UPDATE users SET ira_limit = ? WHERE id = ?",
                   (limit, g.user["id"]))
        db.commit()
        flash("Annual contribution limit updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(request.form.get("back") == "savings"
                    and url_for("portfolio.savings")
                    or url_for("portfolio.settings"))


@bp.route("/settings/accounts/add", methods=("POST",))
@login_required
def accounts_add():
    db = get_db()
    try:
        name = clean_text(request.form.get("name"), field="Account name",
                          max_len=60, required=True)
        kind = require_choice(request.form.get("kind"), ACCOUNT_KINDS,
                              field="Account type")
        exists = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND name = ?",
            (g.user["id"], name)).fetchone()
        if exists:
            raise ValueError(f'You already have an account named "{name}".')
        db.execute("INSERT INTO accounts (user_id, name, kind)"
                   " VALUES (?, ?, ?)", (g.user["id"], name, kind))
        db.commit()
        flash(f'Account "{name}" added.', "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.settings"))


@bp.route("/settings/accounts/<int:account_id>/edit", methods=("POST",))
@login_required
def accounts_edit(account_id):
    db = get_db()
    _own_account_or_404(db, account_id)
    try:
        name = clean_text(request.form.get("name"), field="Account name",
                          max_len=60, required=True)
        kind = require_choice(request.form.get("kind"), ACCOUNT_KINDS,
                              field="Account type")
        db.execute(
            "UPDATE accounts SET name = ?, kind = ? WHERE id = ?"
            " AND user_id = ?", (name, kind, account_id, g.user["id"]))
        db.commit()
        flash("Account updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("portfolio.settings"))


@bp.route("/settings/accounts/<int:account_id>/delete", methods=("POST",))
@login_required
def accounts_delete(account_id):
    db = get_db()
    _own_account_or_404(db, account_id)
    # ON DELETE CASCADE removes the account's holdings/trades/income.
    db.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?",
               (account_id, g.user["id"]))
    db.commit()
    flash("Account and all its data deleted.", "success")
    return redirect(url_for("portfolio.settings"))


@bp.route("/settings/sessions/<int:session_id>/revoke", methods=("POST",))
@login_required
def sessions_revoke(session_id):
    db = get_db()
    cur = db.execute("DELETE FROM sessions WHERE id = ? AND user_id = ?",
                     (session_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash("Session revoked.", "success")
    return redirect(url_for("portfolio.settings"))


@bp.route("/settings/delete-account", methods=("POST",))
@login_required
def delete_account():
    db = get_db()
    password = request.form.get("password") or ""
    if not verify_password(g.user["pw_hash"], password):
        flash("Password incorrect. Your account was NOT deleted.", "error")
        return redirect(url_for("portfolio.settings"))
    db.execute("DELETE FROM users WHERE id = ?", (g.user["id"],))
    db.commit()
    resp = redirect(url_for("portfolio.landing"))
    resp.delete_cookie("cairn_session", path="/")
    flash("Your account and all data have been permanently deleted.",
          "success")
    return resp
