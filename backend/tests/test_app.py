import os
import tempfile
from pathlib import Path

# Must be set before backend.app.db is first imported (anywhere), since it
# reads DATABASE_URL at module import time.
_TEST_DB = Path(tempfile.mkdtemp()) / "test_app.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRIV_DIR = REPO_ROOT / "priv"
STATEMENT_PATH = PRIV_DIR / "2026-06-28_Bank A_C_Statement.pdf"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _ingest(client, account: str):
    with open(STATEMENT_PATH, "rb") as f:
        return client.post(
            "/statements",
            data={"account": account, "bank": "hsbc"},
            files={"file": ("statement.pdf", f, "application/pdf")},
        )


def test_ingest_stage_and_categorize_flow(client):
    resp = _ingest(client, "app-test-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_first_statement"] is True
    assert len(body["newly_staged"]) == 39

    pending = client.get("/pending", params={"account": "app-test-1"}).json()
    assert len(pending) == 39

    first_id = pending[0]["id"]
    resp2 = client.post(f"/pending/{first_id}/categorize", json={"category": "expenses:test"})
    assert resp2.status_code == 200

    rest_ids = [p["id"] for p in pending[1:]]
    resp3 = client.post(
        "/pending/categorize",
        json={"categorizations": {pid: "expenses:misc" for pid in rest_ids}},
    )
    assert resp3.status_code == 200
    assert len(resp3.json()["transaction_ids"]) == 38

    assert client.get("/pending", params={"account": "app-test-1"}).json() == []


def test_reingest_same_statement_is_noop(client):
    _ingest(client, "app-test-2")

    resp = _ingest(client, "app-test-2")

    assert resp.json()["newly_staged"] == []
