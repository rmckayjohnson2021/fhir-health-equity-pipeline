# Architecture Decisions

## ADR 001: Use DuckDB for the v1 warehouse

Decision: v1 uses DuckDB as the local warehouse.

Why: DuckDB keeps the demo free, fast, and easy to run from a private GitHub repo. It lets the project demonstrate warehouse-style modeling without requiring cloud credentials.

Tradeoff: DuckDB is not the target production platform for a state-scale healthcare data program. The repo documents how the same bronze, silver, and gold pattern can map to BigQuery, Snowflake, or Databricks later.

## ADR 002: Simulate source-system adapters

Decision: v1 uses simulated source systems named `epic_simulated`, `athena_simulated`, and `legacy_pms_simulated`.

Why: The goal is to demonstrate data platform architecture, source routing, validation, quarantine, and analytics modeling without claiming real EHR vendor integration.

Tradeoff: The adapters are intentionally simple. They model integration-engine responsibilities but do not replace real interface engine work.

## ADR 003: Make dbt tests the first governance layer

Decision: dbt tests are treated as a primary project artifact, not an afterthought.

Why: Data quality is central to healthcare analytics. Tests make assumptions visible, repeatable, and CI-friendly.

Tradeoff: dbt tests do not prove clinical correctness. They provide engineering controls for the synthetic demo data.

