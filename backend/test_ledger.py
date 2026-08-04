import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ledger import get_or_create_account
from models import Base


@pytest.fixture
def session():
    """
    Fresh in memory sqlite db per test.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_accounts(session):
    print(get_or_create_account(session, "Assets:Checking:HSBC"))
    print(get_or_create_account(session, "Assets:Checking:HSBC"))
    assert 0
