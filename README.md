# ledgr
personal finance system. currently 3 UK banks - HSBC & Revolut, double-entry ledger + statement ingestion + (WIP) insights layer on top
## ledger core
hierarchal accounts, immutable entires, balance = query the db and calculate, instead of a stored field. balanced-entry invariant enforced on post and posts are idempotent via an external id <- means we use reversal instead of update/delete
## ingestion
HSBC pdf and Revolut Excel/.csv implemented, both with ways to self-validate against the statement's own printed totals. 
## insights
currently planned to have automatic classification, alongside a manual categorisation UI for user to edit incorrect classification or step in for classes that the system doesnt know yet. then, the user would be able to see their stats across multiple accounts, see spending anomalies, and export an anonymised .csv version of their transactions to then be able to use with LLMs.  
