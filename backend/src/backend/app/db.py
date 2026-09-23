import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models import Base

# No DB wiring convention exists yet anywhere in this repo (README says
# "currently unorganised for testing") — sqlite file by default, override via
# DATABASE_URL once real Postgres config exists.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./ledgr.db")

# Fly Postgres (and most managed Postgres providers) hand you a
# "postgres://" or driver-less "postgresql://" URL; SQLAlchemy needs the
# driver named explicitly to use psycopg3 instead of defaulting to the
# (not installed) psycopg2.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
