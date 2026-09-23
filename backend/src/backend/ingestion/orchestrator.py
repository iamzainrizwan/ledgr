from __future__ import annotations

import hashlib
from collections import Counter
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.ingestion.common import (
    ParsedStatement,
    ParsedTransaction,
    check_cross_statement_continuity,
    parse_statement_date,
)
from backend.ledger import Posting, get_balance, get_or_create_account, post_transaction
from backend.models import Account, PendingTransaction, Transaction

OPENING_BALANCE_ACCOUNT = "equity:opening balance"
RECONCILIATION_ACCOUNT = "equity:change_balance"


class PendingTransactionNotFoundError(ValueError):
    """Raised when categorizing a pending transaction id that doesn't exist."""


class StageResult(NamedTuple):
    account_name: str
    is_first_statement: bool
    balance_adjustment: Decimal
    newly_staged: list[PendingTransaction]


def _account_name(user_named_account: str) -> str:
    return f"accounts:checking:{user_named_account}"


def _transaction_external_id(
    account_name: str, txn: ParsedTransaction, occurrence: int
) -> str:
    raw = f"{account_name}|{txn.date}|{txn.description}|{txn.amount}|{occurrence}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _external_ids_for(
    account_name: str, transactions: list[ParsedTransaction]
) -> list[str]:
    occurrence_counts: Counter[tuple[str, str, Decimal]] = Counter()
    external_ids = []
    for txn in transactions:
        key = (txn.date, txn.description, txn.amount)
        occurrence = occurrence_counts[key]
        occurrence_counts[key] += 1
        external_ids.append(_transaction_external_id(account_name, txn, occurrence))
    return external_ids


def stage_statement(
    session: Session, user_named_account: str, parsed: ParsedStatement
) -> StageResult:
    """
    Runs the structural checks (first-statement seeding, continuity against the
    account's computed balance) and stages each not-yet-seen transaction as a
    PendingTransaction for categorization — it does not post any transaction
    legs itself, since it doesn't know their categories.
    """
    account_name = _account_name(user_named_account)
    existing_account = session.scalar(
        select(Account).where(Account.name == account_name)
    )
    is_first_statement = existing_account is None
    balance_adjustment = Decimal("0")

    external_ids = _external_ids_for(account_name, parsed.transactions)
    # seed/adjustment postings have no row of their own on the statement, so
    # they're dated to where the statement starts
    statement_start = min(
        (parse_statement_date(t.date) for t in parsed.transactions), default=None
    )

    posted_ids = set(
        session.scalars(
            select(Transaction.external_id).where(
                Transaction.external_id.in_(external_ids)
            )
        )
    )
    staged_ids = set(
        session.scalars(
            select(PendingTransaction.external_id).where(
                PendingTransaction.external_id.in_(external_ids)
            )
        )
    )
    already_handled = posted_ids | staged_ids

    if external_ids and len(already_handled) == len(external_ids):
        # every transaction in this statement is already posted or already
        # awaiting categorization — a re-ingestion of a statement we've
        # already processed, not a discontinuity or new data.
        return StageResult(
            account_name=account_name,
            is_first_statement=is_first_statement,
            balance_adjustment=Decimal("0"),
            newly_staged=[],
        )

    try:
        get_or_create_account(session, account_name)

        if is_first_statement:
            post_transaction(
                session,
                [
                    Posting(account_name, parsed.opening_balance),
                    Posting(OPENING_BALANCE_ACCOUNT, -parsed.opening_balance),
                ],
                description="Opening balance seed",
                external_id=f"seed:{account_name}",
                date=statement_start,
            )
        else:
            current_balance = get_balance(session, account_name)
            balance_adjustment = check_cross_statement_continuity(
                current_balance, parsed.opening_balance
            )
            if balance_adjustment != 0:
                post_transaction(
                    session,
                    [
                        Posting(account_name, balance_adjustment),
                        Posting(RECONCILIATION_ACCOUNT, -balance_adjustment),
                    ],
                    description=(
                        f"Balance adjustment: ledger showed {current_balance}, "
                        f"statement opens at {parsed.opening_balance}"
                    ),
                    date=statement_start,
                )

        newly_staged: list[PendingTransaction] = []
        for txn, external_id in zip(parsed.transactions, external_ids):
            if external_id in already_handled:
                continue
            pending = PendingTransaction(
                account_name=account_name,
                date=txn.date,
                description=txn.description,
                amount=txn.amount,
                external_id=external_id,
            )
            session.add(pending)
            newly_staged.append(pending)
    except Exception:
        session.rollback()
        raise

    session.commit()

    return StageResult(
        account_name=account_name,
        is_first_statement=is_first_statement,
        balance_adjustment=balance_adjustment,
        newly_staged=newly_staged,
    )


def suggest_category(
    session: Session, account_name: str, description: str
) -> str | None:
    """
    Looks up the most recent already-posted Transaction with this exact
    description and returns whichever of its postings wasn't the source
    account — i.e. the category it was given last time. Derived live from
    ledger history rather than a separate stored mapping, so it can't drift
    out of sync with what's actually posted.
    """
    past_txn = session.scalar(
        select(Transaction)
        .where(Transaction.description == description)
        .order_by(Transaction.created_at.desc())
    )
    if past_txn is None:
        return None
    for entry in past_txn.entries:
        if entry.account.name != account_name:
            return entry.account.name
    return None


def categorize_pending(session: Session, pending_id: str, category: str) -> Transaction:
    pending = session.get(PendingTransaction, pending_id)
    if pending is None:
        raise PendingTransactionNotFoundError(pending_id)

    txn = post_transaction(
        session,
        [
            Posting(pending.account_name, pending.amount),
            Posting(category, -pending.amount),
        ],
        description=pending.description,
        external_id=pending.external_id,
        date=parse_statement_date(pending.date),
    )
    session.delete(pending)
    session.commit()
    return txn


def categorize_pending_bulk(
    session: Session, categorizations: dict[str, str]
) -> list[Transaction]:
    """categorizations maps pending id -> category account name."""
    results = []
    try:
        for pending_id, category in categorizations.items():
            pending = session.get(PendingTransaction, pending_id)
            if pending is None:
                raise PendingTransactionNotFoundError(pending_id)
            txn = post_transaction(
                session,
                [
                    Posting(pending.account_name, pending.amount),
                    Posting(category, -pending.amount),
                ],
                description=pending.description,
                external_id=pending.external_id,
                date=parse_statement_date(pending.date),
            )
            session.delete(pending)
            results.append(txn)
    except Exception:
        session.rollback()
        raise

    session.commit()
    return results
