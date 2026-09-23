# ledgr

personal finance system: a double-entry ledger, statement ingestion for HSBC (PDF) and Revolut (Excel), and a stats view on top.

**[live demo →](https://ledgr-demo.fly.dev)** upload a statement (there are sample files on the upload page), review each transaction, check balances, then see where the money went by category and month. the demo account's history is synthetic, and "reset demo" puts it back.

## ledger core
hierarchical accounts (`expenses:groceries`, `income:salary`), immutable entries, and balances computed by querying the entries rather than stored in a field. the balanced-entry invariant is enforced when a transaction posts, and posts are idempotent via an external id, which is why corrections are reversals rather than updates or deletes.

## ingestion
HSBC PDF and Revolut Excel/.csv parsers, each validating a statement against its own printed opening/closing balance before anything posts. consecutive statements are also checked for continuity against the ledger's balance, and any gap is posted as an explicit reconciliation adjustment instead of silently absorbed.

## review
parsed transactions are staged, not posted. each one gets a category suggestion from ledger history (what that description was filed under last time) and is confirmed one at a time or in bulk, at which point it posts into the ledger with its statement date.

## stats
income, spending and net for any month or all time, spend by category (subcategories roll up), the change vs last month, and a month-by-month chart. derived by query every time, same as balances.

## what's next
automatic categorisation, as a stretch.

## running it
see [`backend/README.md`](backend/README.md).
