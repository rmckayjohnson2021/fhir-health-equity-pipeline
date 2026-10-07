# Unmapped Source Drawer

This report lists synthetic source blobs that could not be mapped into the v1 FHIR resource set. They are retained for provenance and future semantic mapping, but excluded from gold analytics.

- Retained blobs: 3

| Blob | Source | Content type | Status | Semantic hint | Hash prefix | Source file |
|---|---|---|---|---|---|---|
| `blob-7c967c34b0ae` | `epic_simulated` | `text/plain` | `unmapped_retained` | `food_insecurity` | `7c967c34b0ae` | `data\unmapped_source\epic_simulated\care-manager-note-001.txt` |
| `blob-a9639320a79c` | `legacy_pms_simulated` | `application/json` | `unmapped_retained` | `food_insecurity,housing_instability` | `a9639320a79c` | `data\unmapped_source\legacy_pms_simulated\screening-export-001.json` |
| `blob-f049c18690e1` | `athena_simulated` | `text/plain` | `unmapped_retained` | `transportation_barrier,referral_document` | `f049c18690e1` | `data\unmapped_source\athena_simulated\referral-fax-001.txt` |

The drawer preserves lineage without treating unmodeled blobs as analytics-ready facts.
