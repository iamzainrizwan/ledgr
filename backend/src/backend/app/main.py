import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal, get_session, init_db
from backend.app.demo_seed import reset_and_seed
from backend.ingestion.common import StatementParseError, StatementSelfCheckError
from backend.ingestion.hsbc import parse_hsbc_pdf
from backend.ingestion.orchestrator import (
    PendingTransactionNotFoundError,
    _account_name,
    categorize_pending,
    categorize_pending_bulk,
    stage_statement,
    suggest_category,
)
from backend.ingestion.revolut import parse_revolut_excel
from backend.ledger import list_account_balances
from backend.stats import compute_stats
from backend.models import Account, PendingTransaction

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    session = SessionLocal()
    try:
        if session.scalar(select(Account)) is None:
            reset_and_seed(session)
    finally:
        session.close()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def _pending_to_dict(session: Session, pending: PendingTransaction) -> dict:
    return {
        "id": pending.id,
        "account_name": pending.account_name,
        "date": pending.date,
        "description": pending.description,
        "amount": str(pending.amount),
        "suggested_category": suggest_category(
            session, pending.account_name, pending.description
        ),
    }


_PARSERS = {
    "hsbc": (parse_hsbc_pdf, ".pdf"),
    "revolut": (parse_revolut_excel, ".xlsx"),
}


@app.post("/statements")
async def ingest_statement(
    account: str = Form(...),
    bank: Literal["hsbc", "revolut"] = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    parse, suffix = _PARSERS[bank]
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        try:
            parsed = parse(Path(tmp.name))
        except (StatementParseError, StatementSelfCheckError) as e:
            raise HTTPException(422, str(e) or e.__class__.__name__)
        except Exception:
            # The parsers can raise arbitrary library-level errors (pandas,
            # pdfplumber) on genuinely malformed input or a bank/file
            # mismatch — those aren't StatementParseError, but they're still
            # "this upload didn't work", not a server bug.
            raise HTTPException(
                422, f"Couldn't parse this file as a {bank} statement."
            )

    result = stage_statement(session, account, parsed)
    return {
        "account_name": result.account_name,
        "is_first_statement": result.is_first_statement,
        "balance_adjustment": str(result.balance_adjustment),
        "newly_staged": [_pending_to_dict(session, p) for p in result.newly_staged],
    }


@app.get("/pending")
def list_pending(account: str | None = None, session: Session = Depends(get_session)):
    query = select(PendingTransaction)
    if account is not None:
        query = query.where(PendingTransaction.account_name == _account_name(account))
    pendings = session.scalars(query).all()
    return [_pending_to_dict(session, p) for p in pendings]


class CategorizeRequest(BaseModel):
    category: str


@app.post("/pending/{pending_id}/categorize")
def categorize(
    pending_id: str,
    body: CategorizeRequest,
    session: Session = Depends(get_session),
):
    try:
        txn = categorize_pending(session, pending_id, body.category)
    except PendingTransactionNotFoundError:
        raise HTTPException(404, "Pending transaction not found")
    return {"transaction_id": txn.id}


class BulkCategorizeRequest(BaseModel):
    categorizations: dict[str, str]  # pending id -> category


@app.post("/pending/categorize")
def categorize_bulk(
    body: BulkCategorizeRequest, session: Session = Depends(get_session)
):
    try:
        txns = categorize_pending_bulk(session, body.categorizations)
    except PendingTransactionNotFoundError as e:
        raise HTTPException(404, f"Pending transaction not found: {e}")
    return {"transaction_ids": [t.id for t in txns]}


@app.get("/accounts")
def accounts(session: Session = Depends(get_session)):
    return [
        {"name": name, "balance": str(balance)}
        for name, balance in list_account_balances(session)
    ]


@app.get("/stats")
def stats(
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    session: Session = Depends(get_session),
):
    """Income, spending, net and spend by category for one month (YYYY-MM), or all time."""
    return compute_stats(session, month)


@app.post("/demo/reset")
def demo_reset(session: Session = Depends(get_session)):
    """
    Wipes and reseeds the demo ledger. No auth on this API at all, so this is
    the public "put it back to a clean state" button — not something a real
    (non-demo) deployment of this app should expose.
    """
    reset_and_seed(session)
    return {"status": "reset"}
