# Source System Mapping

The source systems in this repository are simulated. They exist to demonstrate how source-specific clinical feeds can be tagged, normalized, and monitored without claiming real production integration with commercial EHR vendors.

Planned simulated sources:

- `epic_simulated`
- `athena_simulated`
- `legacy_pms_simulated`

Each source should map into the same bronze schema:

- `source_system`
- `resource_type`
- `resource_id`
- `ingested_at`
- `raw_json`

In production, this adapter layer could be implemented by an integration engine such as Rhapsody, Mirth, or another interface engine. In this repo, lightweight Python scripts will model the same route, validate, tag, quarantine, and monitor responsibilities.
