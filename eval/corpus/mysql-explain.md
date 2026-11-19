# Analysing MySQL Queries with EXPLAIN

Put `EXPLAIN` in front of a `SELECT` statement and MySQL describes how it would run the query without actually executing it.

## Important columns

- `type` is the access method, from best to worst: `const`, `eq_ref`, `ref`, `range`, `index`, and `ALL`. A value of `ALL` means a full table scan, where every row is read. This is usually the sign of a missing index.
- `key` shows which index MySQL actually chose; `possible_keys` lists candidates.
- `rows` is the estimated number of rows to examine.
- `Extra` carries extra warnings. `Using filesort` means MySQL must sort results in a separate pass rather than reading rows in index order. `Using temporary` means an internal temporary table is needed, common with `GROUP BY`. `Using index` means the query is covered by an index.

## EXPLAIN ANALYZE

From MySQL 8.0.18, `EXPLAIN ANALYZE` actually runs the query and reports real timings and row counts next to the estimates, which exposes cases where the optimizer guessed wrongly.

## Finding slow queries

Enable the slow query log with `slow_query_log = 1` and set the threshold with `long_query_time`, for example 2 seconds. Every statement slower than the threshold is written to the log. The `mysqldumpslow` tool summarises the log by grouping similar queries, so the worst offenders appear first. Then run `EXPLAIN` on each one to decide which index or rewrite is needed.
