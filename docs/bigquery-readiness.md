# BigQuery Readiness

The v1 pipeline should run locally with DuckDB.

BigQuery is an optional future target, not a requirement for the core demo. The dbt project should still be written with portability in mind where practical.

Planned readiness items:

- Keep SQL simple and well documented.
- Isolate warehouse-specific logic when needed.
- Provide an example dbt profile for a future BigQuery target.
- Document how bronze, silver, and gold layers map to BigQuery datasets.
