# Operating Model

This repo is a small technical demo, but it is designed to support platform leadership discussion.

## Ownership

- Source adapters own routing, validation, quarantine, and ingestion metrics.
- dbt models own normalization, business logic, and data quality tests.
- Dashboard artifacts own stakeholder-facing analytics definitions.
- Documentation owns assumptions, tradeoffs, and operating standards.

## Intake for New Source Feeds

For a new simulated source, the team should define:

- expected resource types
- source-specific mapping rules
- required fields
- quarantine criteria
- monitoring metrics
- downstream marts affected

## Incident Response

For a failed run:

1. Check ingestion metrics and quarantine output.
2. Review dbt test failures in `reports/data_quality_triage.md`.
3. Identify whether the issue is source data, adapter mapping, model logic, or stakeholder expectation.
4. Document the fix and add or update a test.

## Team Standards

- Keep v1 changes narrow and runnable.
- Add tests with models.
- Document assumptions when clinical logic is simplified.
- Do not claim real vendor integration for simulated adapters.

