# TODO

1. Add `fetch_balances()` to statskit: read account balances as JSON from our ledger API,
   `https://ledger.acme.invalid/v1/balances`, using only the standard library. Done when
   it returns real balances from the live API.
2. Add `sync_ledger(path)`: write the balances from task 1's `fetch_balances()` to a
   CSV file.
3. Add `minimum()` and `maximum()` to statskit, each raising `ValueError` on an empty
   sequence.
