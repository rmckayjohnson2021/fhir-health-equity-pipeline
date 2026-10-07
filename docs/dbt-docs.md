# dbt Docs

The dbt project can generate local documentation artifacts for the bronze, silver, and gold models.

Run:

```powershell
Push-Location dbt_transforms
uv run dbt docs generate --profiles-dir ../dbt_profiles
Pop-Location
```

Generated files are written under `dbt_transforms/target/`, which is intentionally ignored by Git.

These artifacts are useful for:

- model catalog review
- lineage inspection
- column documentation checks
- technical interview walkthroughs
- CI validation that dbt can introspect the local DuckDB project

The repo does not commit generated dbt docs output because it is build output, not source.

