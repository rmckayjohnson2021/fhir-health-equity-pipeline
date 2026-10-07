# Platform KPIs

The v1 demo tracks simple platform health indicators that map to larger data platform operations.

| KPI | Why it matters |
|---|---|
| Records seen | Shows source-feed volume. |
| Records loaded | Shows successful ingestion. |
| Records quarantined | Shows data quality issues caught before modeling. |
| Load success rate | Measures feed reliability by source and resource type. |
| Quarantine rate | Highlights source-specific quality risk. |
| dbt test count | Shows modeled quality coverage. |
| dbt failures or warnings | Shows current modeled data quality risk. |
| Dashboard-ready mart count | Shows delivery of stakeholder-facing data products. |

In a production environment, these KPIs would be monitored over time and connected to incident response, stakeholder communication, and platform investment decisions.

