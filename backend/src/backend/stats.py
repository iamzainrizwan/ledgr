"""
Aggregate stats over the ledger: income, spending, net, spend by category and
by month. Derived by query every time, never stored - same rule as balances.

Sign convention (from the ledger): money leaving checking into an expense is
a positive entry on expenses:*, so spending = sum of expense entries; income
arrives as negative entries on income:*, so income = -sum of income entries.
Reversals are ordinary opposite entries on the same date, so they cancel out
without any special-casing here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.ledger import CHECKING_ACCOUNT_PREFIX, list_account_balances
from backend.models import Account, Entry, Transaction

EXPENSES = "expenses:"
INCOME = "income:"
ZERO = Decimal("0")
CENT = Decimal("0.01")


def _money(d: Decimal) -> str:
    """Every amount leaves as a 2dp string, including an empty month's 0."""
    return str(d.quantize(CENT))


def _month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _previous_month(month: str) -> str:
    year, mon = (int(x) for x in month.split("-"))
    return f"{year - 1:04d}-12" if mon == 1 else f"{year:04d}-{mon - 1:02d}"


def _split_category(account_name: str) -> tuple[str, str | None]:
    """'expenses:food:groceries' -> ('food', 'groceries'); 'expenses:rent' -> ('rent', None)"""
    parts = account_name[len(EXPENSES):].split(":", 1)
    return parts[0], parts[1] if len(parts) > 1 else None


def _load_rows(session: Session) -> list[tuple[str, Decimal, str]]:
    """(account name, amount, month) for every income/expense entry."""
    rows = session.execute(
        select(Account.name, Entry.amount, Transaction.date, Transaction.created_at)
        .join(Entry, Entry.account_id == Account.id)
        .join(Transaction, Transaction.id == Entry.transaction_id)
        .where(or_(Account.name.like(f"{EXPENSES}%"), Account.name.like(f"{INCOME}%")))
    )
    # transactions with no statement behind them fall back to when they were posted
    return [(name, amount, _month_of(d or created.date())) for name, amount, d, created in rows]


def _totals(income: Decimal, spending: Decimal) -> dict:
    net = income - spending
    return {
        "income": _money(income),
        "spending": _money(spending),
        "net": _money(net),
        # share of income kept; undefined with no income rather than a fake 0%
        "savings_rate": None if income == 0 else str((net / income).quantize(Decimal("0.001"))),
    }


def compute_stats(session: Session, month: str | None = None) -> dict:
    """
    Stats for one month ("YYYY-MM"), or all time when month is None. The
    month-by-month history always covers everything, so a chart can show the
    trend around whichever month is selected.
    """
    rows = _load_rows(session)

    by_month: dict[str, dict] = defaultdict(
        lambda: {"income": ZERO, "spending": ZERO, "categories": defaultdict(lambda: ZERO)}
    )
    for name, amount, m in rows:
        bucket = by_month[m]
        if name.startswith(INCOME):
            bucket["income"] -= amount
        else:
            bucket["spending"] += amount
            bucket["categories"][_split_category(name)[0]] += amount

    selected = [r for r in rows if month is None or r[2] == month]
    income = -sum((a for n, a, _ in selected if n.startswith(INCOME)), ZERO)
    spending = sum((a for n, a, _ in selected if n.startswith(EXPENSES)), ZERO)

    categories: dict[str, dict] = {}
    for name, amount, _ in selected:
        if not name.startswith(EXPENSES):
            continue
        top, sub = _split_category(name)
        cat = categories.setdefault(top, {"total": ZERO, "subcategories": defaultdict(lambda: ZERO)})
        cat["total"] += amount
        if sub is not None:
            cat["subcategories"][sub] += amount

    category_list = [
        {
            "name": top,
            "account": f"{EXPENSES}{top}",
            "total": _money(c["total"]),
            "share": None if spending == 0 else str((c["total"] / spending).quantize(Decimal("0.001"))),
            "subcategories": [
                {"name": sub, "account": f"{EXPENSES}{top}:{sub}", "total": _money(t)}
                for sub, t in sorted(c["subcategories"].items(), key=lambda kv: -kv[1])
            ],
        }
        for top, c in sorted(categories.items(), key=lambda kv: -kv[1]["total"])
        # a category fully refunded/reversed in this period has nothing to show
        if c["total"] != 0
    ]

    previous = None
    if month is not None:
        prev = by_month.get(_previous_month(month))
        if prev is not None:
            previous = {"month": _previous_month(month), **_totals(prev["income"], prev["spending"])}

    return {
        "month": month,
        "months": sorted(by_month),
        "totals": _totals(income, spending),
        "previous": previous,
        "categories": category_list,
        "by_month": [
            {
                "month": m,
                "income": _money(b["income"]),
                "spending": _money(b["spending"]),
                "categories": {k: _money(v) for k, v in b["categories"].items()},
            }
            for m, b in sorted(by_month.items())
        ],
        "balances": [
            {"name": name, "balance": str(balance)}
            for name, balance in list_account_balances(session)
            if name.startswith(CHECKING_ACCOUNT_PREFIX)
        ],
    }
