from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid():
    return str(uuid.uuid4())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    entries: Mapped[list["Entry"]] = relationship(back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # when the money moved, per the statement - not when it was posted.
    # nullable for transactions with no statement behind them; stats fall
    # back to created_at for those.
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    external_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    reverses_transaction_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("transactions.id"), nullable=True
    )
    entries: Mapped[list["Entry"]] = relationship(back_populates="transaction")


class PendingTransaction(Base):
    """
    A parsed transaction staged for review before it's categorized and posted.
    Deleted once categorized — this is a working queue, not a record; the real
    record of truth is Transaction/Entry once posting happens.
    """

    __tablename__ = "pending_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    account_name: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (CheckConstraint("amount != 0", name="entry_amount_nonzero"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.id"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="entries")
    account: Mapped["Account"] = relationship(back_populates="entries")
