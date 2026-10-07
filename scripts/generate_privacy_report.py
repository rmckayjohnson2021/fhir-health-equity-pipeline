"""Generate a synthetic PHI-minimization and masking report."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import duckdb


DEFAULT_DATABASE = Path("data/warehouse/health_equity.duckdb")
DEFAULT_OUTPUT_PATH = Path("reports/privacy_masking_report.md")


def fetch_rows(connection: duckdb.DuckDBPyConnection, query: str) -> list[tuple[Any, ...]]:
    return connection.sql(query).fetchall()


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    return connection.sql(query).fetchone()[0]


def table_exists(connection: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    return bool(
        connection.sql(
            """
            select count(*)
            from information_schema.tables
            where table_schema || '.' || table_name = ?
            """,
            params=[table_name],
        ).fetchone()[0]
    )


def table(headers: list[str], rows: list[tuple[Any, ...]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join("" if value is None else str(value) for value in row) + " |")
    return lines


def build_report(database: Path) -> str:
    if not database.exists():
        return "\n".join(
            [
                "# Privacy Masking Report",
                "",
                "The local warehouse does not exist yet. Run the demo before generating this report.",
                "",
            ]
        )

    with duckdb.connect(str(database), read_only=True) as connection:
        if not table_exists(connection, "main_gold.mart_masked_patient_panel"):
            return "\n".join(
                [
                    "# Privacy Masking Report",
                    "",
                    "The masked analytics mart was not available in the latest run.",
                    "",
                    "This usually means dbt stopped before gold models were built. Inspect `reports/data_quality_triage.md` and `reports/gold_promotion_review.md` before promoting data.",
                    "",
                ]
            )

        raw_patient_count = scalar(connection, "select count(*) from main_silver.stg_fhir_patients")
        masked_patient_count = scalar(connection, "select count(*) from main_gold.mart_masked_patient_panel")
        masked_rows = fetch_rows(
            connection,
            """
            select
                masked_patient_key,
                preferred_language,
                zip3_masked,
                age_band,
                last_a1c_month,
                a1c_value_band,
                has_contact_method,
                outreach_channel
            from main_gold.mart_masked_patient_panel
            order by masked_patient_key
            limit 10
            """,
        )

    lines = [
        "# Privacy Masking Report",
        "",
        "This report demonstrates PHI-minimization patterns using synthetic data only. It is not a HIPAA compliance attestation.",
        "",
        "## Summary",
        "",
        f"- Raw synthetic patient rows: {raw_patient_count}",
        f"- Masked analytics rows: {masked_patient_count}",
        "- Direct names: excluded from the masked mart",
        "- Patient IDs: tokenized with a deterministic hash prefix",
        "- Phone numbers: converted to a boolean contact-method flag",
        "- Postal codes: generalized to ZIP3 plus masking suffix",
        "- A1c dates: bucketed to month",
        "- A1c values: bucketed into analytic bands",
        "",
        "## Masked Analytics Sample",
        "",
    ]
    lines.extend(
        table(
            [
                "Masked patient key",
                "Language",
                "ZIP3",
                "Age band",
                "A1c month",
                "A1c band",
                "Contact method",
                "Outreach",
            ],
            masked_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Control Notes",
            "",
            "- Bronze keeps raw synthetic payloads for lineage and debugging.",
            "- Silver normalizes internal clinical entities.",
            "- Gold analytics can default to `mart_masked_patient_panel` when direct identifiers are not needed.",
            "- Production HIPAA controls would still require access policy, audit logging, encryption, environment hardening, BAAs, and formal risk assessment.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a synthetic privacy masking report.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args.database)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(report, encoding="utf-8", newline="\n")
    print(f"Wrote privacy masking report to {args.output_path}")


if __name__ == "__main__":
    main()
