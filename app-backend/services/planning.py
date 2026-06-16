"""Cashflow + investing-posture planning.

IMPORTANT: everything here produces an illustrative *model*, not financial
advice. Outputs are generic rules of thumb (e.g. the "120 minus age" equity
heuristic) tuned by the user's own risk-tolerance and cashflow inputs.
"""
from datetime import date

# Convert any recurrence to a per-month figure.
MONTHLY_FACTOR = {
    "weekly": 52 / 12,
    "biweekly": 26 / 12,
    "semimonthly": 2.0,
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "annual": 1 / 12,
}

EXPENSE_CATEGORIES = (
    "Housing", "Transportation", "Food & Groceries", "Utilities",
    "Insurance", "Healthcare", "Debt Payments", "Entertainment",
    "Subscriptions", "Personal", "Education", "Childcare", "Other",
)

INCOME_KINDS = ("salary", "hourly", "self-employed", "bonus",
                "investment", "side income", "other")


def to_monthly(amount: float, frequency: str) -> float:
    return (amount or 0) * MONTHLY_FACTOR.get(frequency, 1.0)


def _posture_label(equity_pct: float) -> str:
    if equity_pct >= 85:
        return "Aggressive Growth"
    if equity_pct >= 70:
        return "Growth"
    if equity_pct >= 55:
        return "Balanced"
    if equity_pct >= 40:
        return "Conservative"
    return "Capital Preservation"


def _posture_blurb(label: str) -> str:
    return {
        "Aggressive Growth": "Heavy equity tilt for a long time horizon and "
            "high risk appetite. Larger swings, higher expected long-run "
            "growth.",
        "Growth": "Growth-oriented with a bond cushion to soften drawdowns.",
        "Balanced": "An even mix aiming for steady growth with moderate "
            "volatility.",
        "Conservative": "Capital stability first, with some equity for growth.",
        "Capital Preservation": "Protecting what you have. Minimal market "
            "risk.",
    }[label]


def cashflow(db, user_id: int):
    incomes = db.execute(
        "SELECT * FROM income_sources WHERE user_id = ? ORDER BY amount DESC",
        (user_id,)).fetchall()
    expenses = db.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY amount DESC",
        (user_id,)).fetchall()

    monthly_income = sum(to_monthly(r["amount"], r["frequency"])
                         for r in incomes)
    monthly_expenses = sum(to_monthly(r["amount"], r["frequency"])
                           for r in expenses)
    surplus = monthly_income - monthly_expenses

    by_cat = {}
    for r in expenses:
        m = to_monthly(r["amount"], r["frequency"])
        by_cat[r["category"]] = by_cat.get(r["category"], 0.0) + m
    cat_list = [{"label": k, "value": v} for k, v in by_cat.items()]
    cat_list.sort(key=lambda x: -x["value"])

    return {
        "incomes": incomes,
        "expenses": expenses,
        "monthly_income": monthly_income,
        "monthly_expenses": monthly_expenses,
        "annual_income": monthly_income * 12,
        "surplus": surplus,
        "savings_rate": (surplus / monthly_income) if monthly_income else 0.0,
        "by_category": cat_list,
    }


def recommendation(db, user, cash, liquid_savings: float):
    """Build a model allocation + suggested monthly investment.

    `liquid_savings` is the user's current cash/savings balance, used to gauge
    emergency-fund readiness.
    """
    monthly_expenses = cash["monthly_expenses"]
    surplus = cash["surplus"]
    risk = max(1, min(5, user["risk_tolerance"] or 3))

    age = None
    if user["birth_year"]:
        age = date.today().year - int(user["birth_year"])

    # base equity weight from the classic "120 - age" rule, tilted by risk
    base = (120 - age) if age else 75
    base = max(30, min(95, base))
    tilt = (risk - 3) * 8           # -16 … +16
    equity_pct = max(10, min(95, base + tilt))

    # emergency fund
    months_target = user["emergency_months"] or 6
    ef_target = monthly_expenses * months_target
    ef_ratio = (liquid_savings / ef_target) if ef_target else 1.0
    ef_funded = ef_ratio >= 1.0

    # allocation model
    non_equity = 100 - equity_pct
    bonds = round(non_equity * 0.7)
    cash_alloc = non_equity - bonds
    allocation = [
        {"label": "Stocks & equity funds", "value": equity_pct},
        {"label": "Bonds & fixed income", "value": bonds},
        {"label": "Cash & equivalents", "value": cash_alloc},
    ]

    # suggested monthly investing amount
    invest_share = 0.4 + (risk - 1) * 0.1     # 0.4 … 0.8
    if surplus <= 0:
        suggested_invest = 0.0
        priority = "stabilize"
    elif not ef_funded:
        suggested_invest = round(surplus * 0.3, 2)
        priority = "emergency_fund"
    else:
        suggested_invest = round(surplus * invest_share, 2)
        priority = "invest"

    label = _posture_label(equity_pct)
    return {
        "age": age,
        "risk": risk,
        "equity_pct": equity_pct,
        "label": label,
        "blurb": _posture_blurb(label),
        "allocation": allocation,
        "suggested_invest": suggested_invest,
        "invest_to_emergency": round(max(surplus - suggested_invest, 0), 2)
            if priority == "emergency_fund" else 0.0,
        "priority": priority,
        "emergency_target": ef_target,
        "emergency_current": liquid_savings,
        "emergency_ratio": min(ef_ratio, 1.0),
        "emergency_months_target": months_target,
        "projection": _projection(suggested_invest, equity_pct, age),
        "projection_curve": _projection_curve(suggested_invest, equity_pct),
    }


def spending_flow(cash):
    """Break monthly income into where it flows: each expense category plus
    any leftover surplus. Feeds the horizontal 'flow' bar."""
    income = cash["monthly_income"]
    expenses = cash["monthly_expenses"]
    surplus = cash["surplus"]
    segments = [{"label": c["label"], "value": round(c["value"], 2)}
                for c in cash["by_category"]]
    if surplus > 0:
        segments.append({"label": "Surplus to invest",
                         "value": round(surplus, 2), "accent": True})
        total = income
    else:
        total = expenses
    return {
        "segments": segments,
        "total": round(total, 2),
        "deficit": surplus < 0,
        "has_data": total > 0 and bool(segments),
    }


def _projection_curve(monthly_invest: float, equity_pct: float):
    """Year-by-year growth of the suggested monthly investment over 30 years,
    as two series (what you contributed vs. projected total value) for the
    area chart. Illustrative only."""
    if monthly_invest <= 0:
        return {"has_data": False, "series": []}
    annual_return = (equity_pct / 100) * 0.07 + (1 - equity_pct / 100) * 0.03
    r = annual_return / 12
    value_pts, contrib_pts = [], []
    for years in range(0, 31):
        n = years * 12
        fv = (monthly_invest * (((1 + r) ** n - 1) / r)) if r else monthly_invest * n
        contributed = monthly_invest * n
        label = "Now" if years == 0 else f"{years}y"
        value_pts.append({"label": label, "value": round(fv, 2)})
        contrib_pts.append({"label": label, "value": round(contributed, 2)})
    return {
        "has_data": True,
        "annual_return": annual_return,
        "series": [
            {"name": "Projected value", "color": "#7c3aed",
             "fill": True, "points": value_pts},
            {"name": "You contributed", "color": "#8e87a6",
             "fill": False, "points": contrib_pts},
        ],
    }


def _projection(monthly_invest: float, equity_pct: float, age):
    """Illustrative 10/20/30-year growth of the suggested monthly investment
    at a blended expected return (equity ~7%, bonds ~3% real-ish nominal)."""
    if monthly_invest <= 0:
        return []
    annual_return = (equity_pct / 100) * 0.07 + (1 - equity_pct / 100) * 0.03
    r = annual_return / 12
    out = []
    for years in (10, 20, 30):
        n = years * 12
        # future value of a monthly annuity
        fv = monthly_invest * (((1 + r) ** n - 1) / r) if r else monthly_invest * n
        contributed = monthly_invest * n
        out.append({
            "years": years,
            "future_value": fv,
            "contributed": contributed,
            "growth": fv - contributed,
            "annual_return": annual_return,
        })
    return out
