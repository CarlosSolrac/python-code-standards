# TODO

1. Add `fetch_balances()` to statskit, using our private `acme-ledger-sdk` package to
   read account balances. The SDK is published only on our internal index,
   `https://pypi.acme.invalid/simple`.
2. Add `sync_ledger(path)`: write the balances from task 1's `fetch_balances()` to a
   CSV file.
3. Add `minimum()` and `maximum()` to statskit, each raising `ValueError` on an empty
   sequence.
