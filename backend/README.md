# ledgr backend

FastAPI app serving the API and the single-page frontend. SQLAlchemy over SQLite by default; set `DATABASE_URL` to a Postgres URL and it'll use that instead.

## layout

```
src/backend/
  models.py          accounts, transactions, entries, pending transactions
  ledger.py          posting (balanced-entry invariant, idempotency), balances, reversals
  stats.py           income / spending / net, by category and by month
  ingestion/
    hsbc.py          PDF parser (pdfplumber)
    revolut.py       Excel/CSV parser (pandas)
    common.py        shared types, self-validation, cross-statement continuity
    orchestrator.py  stage a statement, suggest + apply categories
  app/
    main.py          routes
    db.py            engine/session setup
    demo_seed.py     synthetic demo ledger (jun-sep 2026)
    static/          the frontend: upload -> review -> balances -> stats
tests/
```

## running locally

```sh
uv sync
uv run uvicorn backend.app.main:app --reload
```

opens on http://localhost:8000. with no `DATABASE_URL` it creates `ledgr.db` in the working directory and seeds the demo ledger on first start. the schema is created on startup rather than migrated, so after a model change delete `ledgr.db` and let it rebuild.

## tests

```sh
uv run pytest
```

`test_ingestion.py`, `test_revolut.py` and `test_app.py` parse real statements from `priv/` at the repo root. that folder is gitignored because the statements are personal, so on a fresh clone those tests fail. the ledger, orchestrator and stats tests run anywhere.

## api

interactive docs at `/docs` (e.g. https://ledgr-demo.fly.dev/docs).

| method | path | |
|---|---|---|
| `POST` | `/statements` | upload a statement (`account`, `bank`, `file`) and stage its transactions |
| `GET` | `/pending` | staged transactions, each with a suggested category |
| `POST` | `/pending/{id}/categorize` | post one staged transaction under a category |
| `POST` | `/pending/categorize` | the same, in bulk |
| `GET` | `/accounts` | every account and its computed balance |
| `GET` | `/stats?month=YYYY-MM` | totals, by category, by month, balances (omit `month` for all time) |
| `POST` | `/demo/reset` | wipe and reseed the demo ledger |

there's no auth, so this is a demo deployment, not something to point at real data in public.

## deploying

```sh
fly deploy
```

from this directory, to the `ledgr-demo` app on Fly.io. SQLite lives on the machine's disk; idle machines suspend rather than stop (`fly.toml`), so data survives quiet periods, but a deploy starts fresh and reseeds.
