"""Portfolio math.

Fixes baked in (vs. the original Excel workbook):
- Average cost basis is computed from trade history, never typed by hand.
- Realized P&L on a sell always uses the holding's live average cost.
- "Without retirement" totals are derived from each account's kind flag,
  so cash-management accounts are never silently dropped.
- Aggregations (by account / asset type / industry) are grouped from the
  data itself — a new account can never be missing from a breakdown.
"""
from datetime import date


def _row_value(h) -> float:
    return (h["quantity"] or 0) * (h["current_price"] or 0)


def _row_cost(h) -> float:
    return (h["quantity"] or 0) * (h["avg_cost"] or 0)


def holdings_with_metrics(db, user_id: int):
    rows = db.execute(
        "SELECT h.*, a.name AS account_name, a.kind AS account_kind"
        " FROM holdings h JOIN accounts a ON a.id = h.account_id"
        " WHERE h.user_id = ?"
        " ORDER BY (h.quantity * h.current_price) DESC, h.ticker",
        (user_id,),
    ).fetchall()
    out = []
    for h in rows:
        d = dict(h)
        d["market_value"] = _row_value(h)
        d["cost"] = _row_cost(h)
        d["unrealized"] = d["market_value"] - d["cost"]
        d["gl_pct"] = (d["unrealized"] / d["cost"]) if d["cost"] else 0.0
        out.append(d)
    return out


def portfolio_summary(db, user_id: int, include_retirement: bool = True):
    holdings = holdings_with_metrics(db, user_id)
    if not include_retirement:
        scoped = [h for h in holdings if h["account_kind"] != "retirement"]
    else:
        scoped = holdings

    total_value = sum(h["market_value"] for h in scoped)
    total_cost = sum(h["cost"] for h in scoped)
    unrealized = total_value - total_cost

    def grouped(key):
        groups = {}
        for h in scoped:
            label = h[key] or "Uncategorized"
            groups[label] = groups.get(label, 0.0) + h["market_value"]
        items = [
            {"label": k, "value": v,
             "pct": (v / total_value) if total_value else 0.0}
            for k, v in groups.items() if round(v, 2) != 0
        ]
        items.sort(key=lambda x: -x["value"])
        return items

    return {
        "holdings": scoped,
        "all_holdings": holdings,
        "total_value": total_value,
        "total_cost": total_cost,
        "unrealized": unrealized,
        "unrealized_pct": (unrealized / total_cost) if total_cost else 0.0,
        "by_account": grouped("account_name"),
        "by_asset_type": grouped("asset_type"),
        "by_industry": grouped("industry"),
    }


def apply_trade(db, user_id: int, *, account_id: int, trade_date: str,
                asset_type: str, ticker: str, action: str, quantity: float,
                price: float, note: str = ""):
    """Record a trade and keep the matching holding consistent.

    Returns the realized P&L for sells (None for buys).
    Raises ValueError on impossible trades (e.g. selling more than held).
    """
    ticker = ticker.upper()
    holding = db.execute(
        "SELECT * FROM holdings WHERE user_id = ? AND account_id = ?"
        " AND ticker = ? AND asset_type = ?",
        (user_id, account_id, ticker, asset_type),
    ).fetchone()

    cost_basis = None
    realized = None

    if action == "Buy":
        if holding:
            old_qty = holding["quantity"] or 0
            new_qty = old_qty + quantity
            new_avg = ((old_qty * (holding["avg_cost"] or 0)
                        + quantity * price) / new_qty) if new_qty > 0 else price
            db.execute(
                "UPDATE holdings SET quantity = ?, avg_cost = ?,"
                " current_price = ?, price_updated_at = datetime('now')"
                " WHERE id = ? AND user_id = ?",
                (new_qty, new_avg, price, holding["id"], user_id),
            )
        else:
            db.execute(
                "INSERT INTO holdings (user_id, account_id, asset_type,"
                " ticker, name, quantity, avg_cost, current_price,"
                " price_updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (user_id, account_id, asset_type, ticker, ticker,
                 quantity, price, price),
            )
    else:  # Sell
        held = (holding["quantity"] or 0) if holding else 0
        if held + 1e-9 < quantity:
            raise ValueError(
                f"You only hold {held:g} {ticker} in that account, "
                f"so you can't sell {quantity:g}.")
        cost_basis = holding["avg_cost"] or 0
        realized = (price - cost_basis) * quantity
        new_qty = max(held - quantity, 0.0)
        db.execute(
            "UPDATE holdings SET quantity = ?, current_price = ?,"
            " price_updated_at = datetime('now')"
            " WHERE id = ? AND user_id = ?",
            (new_qty, price, holding["id"], user_id),
        )

    db.execute(
        "INSERT INTO trades (user_id, account_id, trade_date, asset_type,"
        " ticker, action, quantity, price, cost_basis, realized_pl, note)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, account_id, trade_date, asset_type, ticker, action,
         quantity, price, cost_basis, realized, note),
    )
    db.commit()
    return realized


def trade_stats(db, user_id: int, year: int | None = None):
    where = "user_id = ?"
    params: list = [user_id]
    if year:
        where += " AND trade_date >= ? AND trade_date <= ?"
        params += [f"{year}-01-01", f"{year}-12-31"]
    row = db.execute(
        f"SELECT COALESCE(SUM(realized_pl), 0) AS realized,"
        f" SUM(CASE WHEN realized_pl > 0 THEN 1 ELSE 0 END) AS wins,"
        f" SUM(CASE WHEN realized_pl < 0 THEN 1 ELSE 0 END) AS losses,"
        f" COUNT(*) AS total"
        f" FROM trades WHERE {where}", params,
    ).fetchone()
    return {
        "realized": row["realized"] or 0.0,
        "wins": row["wins"] or 0,
        "losses": row["losses"] or 0,
        "total": row["total"] or 0,
    }


def income_summary(db, user_id: int, year: int | None = None):
    where = "i.user_id = ?"
    params: list = [user_id]
    if year:
        where += " AND i.income_date >= ? AND i.income_date <= ?"
        params += [f"{year}-01-01", f"{year}-12-31"]

    by_type = db.execute(
        f"SELECT i.type AS label, SUM(i.amount) AS value FROM incomes i"
        f" WHERE {where} GROUP BY i.type ORDER BY value DESC", params,
    ).fetchall()
    by_account = db.execute(
        f"SELECT a.name AS label, SUM(i.amount) AS value FROM incomes i"
        f" JOIN accounts a ON a.id = i.account_id"
        f" WHERE {where} GROUP BY a.name ORDER BY value DESC", params,
    ).fetchall()
    total = db.execute(
        f"SELECT COALESCE(SUM(i.amount), 0) AS t FROM incomes i WHERE {where}",
        params,
    ).fetchone()["t"]
    return {
        "by_type": [dict(r) for r in by_type],
        "by_account": [dict(r) for r in by_account],
        "total": total or 0.0,
    }


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _monthly_series(rows):
    """Bucket rows of {d: 'YYYY-MM-DD…', v: amount} into 12 calendar months.

    Returns [{label, value}] of length 12 plus a `has_data` flag, ready to feed
    the bar-chart renderer.
    """
    buckets = [0.0] * 12
    for r in rows:
        d = r["d"] or ""
        if len(d) >= 7:
            try:
                m = int(d[5:7])
            except ValueError:
                continue
            if 1 <= m <= 12:
                buckets[m - 1] += (r["v"] or 0)
    points = [{"label": _MONTHS[i], "value": round(buckets[i], 2)}
              for i in range(12)]
    return points, any(b for b in buckets)


def monthly_income_series(db, user_id: int, year: int | None = None):
    """Dividend + interest income per month for the given year."""
    year = year or date.today().year
    rows = db.execute(
        "SELECT income_date AS d, amount AS v FROM incomes"
        " WHERE user_id = ? AND income_date >= ? AND income_date <= ?",
        (user_id, f"{year}-01-01", f"{year}-12-31"),
    ).fetchall()
    points, has_data = _monthly_series(rows)
    return {"points": points, "has_data": has_data, "year": year}


def contributions_series(db, user_id: int, year: int | None = None):
    """Retirement contributions per month for the given year."""
    year = year or date.today().year
    rows = db.execute(
        "SELECT contrib_date AS d, amount AS v FROM contributions"
        " WHERE user_id = ? AND year = ?",
        (user_id, year),
    ).fetchall()
    points, has_data = _monthly_series(rows)
    return {"points": points, "has_data": has_data, "year": year}


def _month_floor(date_str: str) -> str:
    return (date_str or "")[:7]  # YYYY-MM


def _add_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m += 1
    if m > 12:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def growth_series(db, user_id: int):
    """Monthly cumulative 'money earned/lost from investing' = realized P&L
    plus dividend/interest income, charted from first activity to now.

    Returns {points:[{label, value, realized, income}], current_unrealized,
    total_value, has_data}.
    """
    realized_rows = db.execute(
        "SELECT trade_date AS d, COALESCE(realized_pl, 0) AS v FROM trades"
        " WHERE user_id = ? AND realized_pl IS NOT NULL", (user_id,),
    ).fetchall()
    income_rows = db.execute(
        "SELECT income_date AS d, amount AS v FROM incomes WHERE user_id = ?",
        (user_id,),
    ).fetchall()

    realized_by_month: dict[str, float] = {}
    income_by_month: dict[str, float] = {}
    for r in realized_rows:
        ym = _month_floor(r["d"])
        if ym:
            realized_by_month[ym] = realized_by_month.get(ym, 0.0) + (r["v"] or 0)
    for r in income_rows:
        ym = _month_floor(r["d"])
        if ym:
            income_by_month[ym] = income_by_month.get(ym, 0.0) + (r["v"] or 0)

    summary = portfolio_summary(db, user_id, True)
    current_unrealized = summary["unrealized"]

    months = sorted(set(realized_by_month) | set(income_by_month))
    points = []
    if months:
        cur = months[0]
        end = _month_floor(date.today().isoformat()) or months[-1]
        if end < months[-1]:
            end = months[-1]
        cum_r = cum_i = 0.0
        while cur <= end:
            cum_r += realized_by_month.get(cur, 0.0)
            cum_i += income_by_month.get(cur, 0.0)
            points.append({
                "label": cur, "realized": cum_r, "income": cum_i,
                "value": cum_r + cum_i,
            })
            cur = _add_month(cur)

    return {
        "points": points,
        "current_unrealized": current_unrealized,
        "total_value": summary["total_value"],
        "realized_total": points[-1]["realized"] if points else 0.0,
        "income_total": points[-1]["income"] if points else 0.0,
        "has_data": len(points) >= 2,
    }


def record_snapshot(db, user_id: int):
    """Store today's total value (idempotent per day) to build an equity
    curve over time going forward."""
    summary = portfolio_summary(db, user_id, True)
    today = date.today().isoformat()
    db.execute(
        "INSERT INTO snapshots (user_id, snap_date, total_value, cost_basis)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT (user_id, snap_date) DO UPDATE SET"
        " total_value = excluded.total_value, cost_basis = excluded.cost_basis",
        (user_id, today, summary["total_value"], summary["total_cost"]),
    )
    db.commit()


def retirement_progress(db, user, year: int | None = None):
    year = year or date.today().year
    rows = db.execute(
        "SELECT a.name AS label, COALESCE(SUM(c.amount), 0) AS value"
        " FROM contributions c JOIN accounts a ON a.id = c.account_id"
        " WHERE c.user_id = ? AND c.year = ?"
        " GROUP BY a.name ORDER BY value DESC",
        (user["id"], year),
    ).fetchall()
    contributed = sum(r["value"] for r in rows)
    limit = user["ira_limit"] or 0
    return {
        "year": year,
        "by_account": [dict(r) for r in rows],
        "contributed": contributed,
        "limit": limit,
        "remaining": max(limit - contributed, 0),
        "pct": min(contributed / limit, 1.0) if limit else 0.0,
    }
