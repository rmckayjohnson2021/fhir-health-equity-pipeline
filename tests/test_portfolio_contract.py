from pathlib import Path
import unittest

from scripts.generate_fhir_mapping_workbench import FHIR_SCHEMA_SUBSET, FORCED_CONVERSION_TARGET_TYPES
from scripts.generate_synthea_sample import DEFAULT_PATIENT_COUNT, LANGUAGES, SOURCE_SYSTEMS, patient_panel


ROOT = Path(__file__).resolve().parents[1]


class PortfolioContractTests(unittest.TestCase):
    def test_default_synthetic_panel_keeps_expected_language_and_source_contract(self) -> None:
        patients = patient_panel(DEFAULT_PATIENT_COUNT)
        language_names = {patient.language_display for patient in patients}
        language_codes = {code for code, _display in LANGUAGES}
        source_systems = {patient.source_system for patient in patients}

        self.assertEqual(len(patients), 60)
        self.assertEqual(len({patient.patient_id for patient in patients}), 60)
        self.assertEqual(source_systems, set(SOURCE_SYSTEMS))
        self.assertSetEqual(language_names, {"English", "Spanish", "French", "Haitian Creole", "Arabic"})
        self.assertSetEqual(language_codes, {"en", "es", "fr", "ht", "ar"})
        self.assertNotIn("Vietnamese", language_names)

    def test_dashboard_contains_operational_controls(self) -> None:
        dashboard = (ROOT / "dashboards" / "static_preview.html").read_text(encoding="utf-8")

        required_markers = [
            "Source feeds*",
            "System Health",
            "data-health-modal",
            "View Current State",
            "Open Pipeline Monitor",
            "View Detailed Dashboard",
            "Current State",
            "What's in process",
            "Detailed view",
            "data-view-tab=\"current\"",
            "data-view-section=\"current detail\"",
            "Run slow monitor",
            "Run next synthetic load",
            "data-real-load",
            "dashboard_control_server",
            "Dismiss all quarantined",
            "quarantine_archive",
            "Run Fidelity Trend",
            "OpenTelemetry Trace Dashboard",
            "data-otel-trace-dashboard",
            "data-patient-table",
            "Export CSV",
            "data-start-date",
            "data-end-date",
            "data-floating-tooltip",
            "portfolio-footer",
            "GitHub repo",
            "LinkedIn profile",
            "https://github.com/rmckayjohnson2021/fhir-health-equity-pipeline",
            "https://www.linkedin.com/in/mckayjohnson/",
            "Synthetic data only - no real patient records or real EHR integrations",
        ]
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, dashboard)

        former_employer_marker = "Green" + "way"
        forbidden_markers = [former_employer_marker, "Vietnamese", "17 valid", "17 synthetic"]
        for marker in forbidden_markers:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, dashboard)

    def test_fhir_mapping_workbench_versions_and_forced_conversion(self) -> None:
        workbench = (ROOT / "dashboards" / "fhir_mapping_workbench.html").read_text(encoding="utf-8")

        self.assertEqual(FHIR_SCHEMA_SUBSET["R4"]["release"], "4.0")
        self.assertEqual(FHIR_SCHEMA_SUBSET["R4B"]["release"], "4.3")
        self.assertEqual(FHIR_SCHEMA_SUBSET["R5"]["release"], "5.0")
        self.assertEqual(
            FHIR_SCHEMA_SUBSET["R5"]["mappingSupport"]["food_access_text"]["status"],
            "supported",
        )
        self.assertIn("Simulate but do not apply", workbench)
        self.assertIn("forced conversion blocked: note is required", workbench)
        self.assertIn("Allowed forced FHIR type", workbench)
        self.assertIn("forced_mappings", workbench)
        self.assertIn("DocumentReference", workbench)
        self.assertIn("R5 / 5.0", workbench)
        self.assertIn("portfolio-footer", workbench)
        self.assertIn("GitHub repo", workbench)
        self.assertIn("LinkedIn profile", workbench)
        self.assertIn("DocumentReference", FORCED_CONVERSION_TARGET_TYPES)

    def test_readme_references_current_screenshots(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("dashboards/screenshots/static-preview.png", readme)
        self.assertIn("dashboards/screenshots/dashboard-system-health.png", readme)
        self.assertIn("dashboards/screenshots/dashboard-process-view.png", readme)
        self.assertIn("dashboards/screenshots/dashboard-detail-view.png", readme)
        self.assertIn("dashboards/screenshots/fhir-mapping-workbench.png", readme)
        self.assertIn("dashboards/assets/logo-transparent.png", readme)
        self.assertIn("Feature Coverage Sanity Check", readme)
        self.assertIn("```mermaid", readme)
        self.assertIn("What Would Make This Production Usable", readme)
        discouraged_cost_word = "ch" + "eap"
        self.assertNotIn(discouraged_cost_word, readme.lower())
        self.assertTrue((ROOT / "docs" / "full-feature-demo-script.md").exists())
        self.assertTrue((ROOT / "scripts" / "dashboard_control_server.py").exists())


if __name__ == "__main__":
    unittest.main()
