# Cloud Platform Readiness

The v1 demo runs locally with DuckDB. That is a deliberate cost and usability choice.

## BigQuery Pattern

- Bronze, silver, and gold schemas map to datasets.
- dbt models can target BigQuery through a separate profile.
- CI should avoid cloud credentials unless a secure deployment path exists.

## Snowflake Pattern

- Bronze, silver, and gold schemas map to Snowflake schemas.
- Warehouse sizing and auto-suspend become cost controls.
- Access roles would separate raw data, modeled data, and analytics consumers.

## Databricks Pattern

- Bronze, silver, and gold layers map naturally to lakehouse medallion architecture.
- Spark becomes useful when source volume or file size exceeds local or warehouse-only workflows.
- Jobs or workflows would replace the local Makefile for orchestration.

## Orchestration Pattern

The local v1 command sequence is:

```text
generate synthetic data -> ingest FHIR -> dbt build -> triage report
```

In production, this could become an Airflow DAG, Databricks workflow, or cloud-native scheduled job with alerts and retry policy.

