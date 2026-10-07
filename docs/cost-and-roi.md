# Cost and ROI

The v1 project is intentionally local-first.

## Cost-Aware Choices

- DuckDB avoids cloud warehouse spend for the demo.
- dbt Core avoids paid transformation tooling.
- Synthetic data avoids PHI risk and compliance overhead.
- Saved SQL and screenshots can demonstrate dashboards without requiring hosted BI.
- Deterministic scripts avoid paid AI usage.

## Cloud Cost Questions for Later

If this pattern moved to BigQuery, Snowflake, or Databricks, the key cost questions would be:

- How much data is ingested per day?
- How often do models rebuild?
- Which marts need freshness guarantees?
- Which users need self-service query access?
- What data quality checks should run on every load versus scheduled audits?
- Which workloads need Spark-scale processing and which can stay in warehouse SQL?

## ROI Story

The business value is not only faster ETL. The value is trusted healthcare analytics: fewer manual reconciliations, clearer source-quality issues, faster care-gap reporting, and better confidence in stakeholder-facing metrics.

