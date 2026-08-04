from __future__ import annotations

from decimal import Decimal
from typing import Iterable, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, Entry, Transaction


class Posting(NamedTuple):
    """
    account name and signed amount
    """

    account: str
    amount: Decimal


class UnbalancedTransactionError(ValueError):
    """Raises when a set of postings don't sum to 0"""


class InsufficientPostingsError(ValueError):
    """Raises when fewer than 2 postings are given"""


class TransactionNotFoundError(ValueError):
    """Raises when attempting to reverse a Transaction that does not exist"""


class TransactionAlreadyReversedError(ValueError):
    """Raises when attempting to reverse a Transaction that has aleady been reversed"""


class CannotReverseReversalError(ValueError):
    """Raises when trying to reverse an already reversed Transaction"""


def get_or_create_account(session: Session, name: str) -> Account:
    """
    Look up an account by name. If it doesn't exist, create it.

    Calling this twice with the same name should return the same Account, not create a dupe.
    """
    account = session.scalar(select(Account).where(Account.name == name))

    if account is None:
        account = Account(name=name)
        session.add(account)
        session.flush()

    return account


def post_transaction(
    session: Session,
    postings: Iterable[Posting],
    *,
    description: str | None = None,
    external_id: str | None = None,
    reverses_transaction_id: str | None = None,
) -> Transaction:
    """
    Posts a balanced set of entries as one Transaction.
    1. Idempotency: if given an external_id that exists in a Transaction, return that Transaction
    2. At least two postings
    3. Postings must sum to exactly 0.0
    """
    if external_id is not None:
        existing = session.scalar(
            select(Transaction).where(Transaction.external_id == external_id)
        )
        if existing is not None:
            return existing

    postings = list(postings)
    txn = Transaction(
        description=description,
        external_id=external_id,
        reverses_transaction_id=reverses_transaction_id,
    )
    session.add(txn)
    session.flush()

    if len(postings) < 2:
        raise InsufficientPostingsError()

    sum = Decimal("0")
    for p in postings:
        sum += p.amount
        account = get_or_create_account(session, p.account)
        entry = Entry(
            transaction_id=txn.id,
            account_id=account.id,
            amount=p.amount,
        )
        session.add(entry)

    if sum != Decimal("0"):
        raise UnbalancedTransactionError()

    session.commit()
    return txn


def get_balance(
    session: Session, account_name: str, *, include_children: bool
) -> Decimal:
    if not include_children:
        account = session.scalar(select(Account).where(Account.name == account_name))
        if account is None:
            return Decimal("0")
        total = Decimal("0")
        for e in account.entries:
            total += e.amount
        return total
    else:
        accounts = session.scalars(
            select(Account).where(
                (Account.name == account_name)
                | (Account.name.like(f"{account_name}:%"))
            )
        )
        total = Decimal("0")
        for a in accounts:
            for e in a.entries:
                total += e.amount
        return total


def reverse_transaction(
    session: Session, transaction_id: str, *, description: str | None = None
) -> Transaction:
    original_txn = session.scalar(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    if original_txn is None:
        raise TransactionNotFoundError()
    if original_txn.reverses_transaction_id is not None:
        raise CannotReverseReversalError()

    existing = session.scalar(
        select(Transaction).where(Transaction.reverses_transaction_id == transaction_id)
    )
    if existing is not None:
        raise TransactionAlreadyReversedError()

    reversal_postings = [
        Posting(
            account=e.account.name,
            amount=-e.amount,
        )
        for e in original_txn.entries
    ]

    return post_transaction(
        session,
        reversal_postings,
        description=description,
        reverses_transaction_id=original_txn.id,
    )
