# tally

Totals daily revenue from an orders CSV.

```bash
uv sync
uv run tally orders.csv report.csv
```

The input has the header `order_id,day,amount`, with amounts in whole cents (`10.50`); a later row with the same `order_id` replaces
an earlier one. The report has the header `day,revenue`, earliest day first. A malformed row stops the run with exit code 1 and
names its line.
