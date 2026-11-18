# Backlog

1. Accept a `--since` date so the report can cover part of the file.
2. `tally-stage` still declares `tally-io` from before `load_orders` took an `OrderSource`; nothing in `tally-stage` imports
   `tally_io`. Remove the declaration and run `uv lock`.
3. Write the report as Parquet as well as CSV.
