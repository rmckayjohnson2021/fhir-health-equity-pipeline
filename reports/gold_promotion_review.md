# Gold Promotion Review

This report identifies synthetic records or model failures that should not feed gold analytics until a stewardship decision is made.

Gold promotion means the data is safe enough to appear in dashboard-ready marts. Bronze landing alone is not treated as approval for stakeholder reporting.

## Summary

- Review items: 1
- `request_source_correction`: 1

## Decision Queue

| Issue | Source | Resource | Reason | Decision | Evidence |
|---|---|---|---|---|---|
| `quarantine-legacy_pms_simulated-Observation-1` | `legacy_pms_simulated` | `Observation/missing-id` | missing required FHIR resource id | `request_source_correction` | `data\batches\batch_012\legacy_pms_simulated\fhir.ndjson:41` |

## Decision Options

- `request_source_correction`: the feed record is invalid for promotion and should be corrected upstream before retry.
- `fix_mapping_and_reprocess`: the payload may be valid, but local mapping rules need to change before promotion.
- `reject_from_gold`: the record remains auditable but is excluded from gold marts.
- `accept_exception_for_monitoring`: a documented exception is allowed only when analytics remain safe.
- `defer`: the item stays open for later stewardship.

