"""T-CERT contract guards for the locked ADR-0009 evidence export."""

import json
from pathlib import Path

import certificate
import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "app" / "gold_export" / "analysis_rigor.json"


def test_committed_certificate_validates_against_its_inputs():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    certificate.validate_certificate(evidence, ROOT)


def test_certificate_rejects_a_tampered_input_hash():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    evidence["certificate"]["input_sha256"]["dbt/seeds/disruption_dates.csv"] = "0" * 64
    try:
        certificate.validate_certificate(evidence, ROOT)
    except ValueError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered certificate must be rejected")


def test_versioned_text_hash_ignores_checkout_line_endings(tmp_path):
    lf = tmp_path / "lf.csv"
    crlf = tmp_path / "crlf.csv"
    lf.write_bytes(b"date,source_url\ndate,https://example.test\n")
    crlf.write_bytes(b"date,source_url\r\ndate,https://example.test\r\n")

    assert certificate.sha256_versioned_text(lf) == certificate.sha256_versioned_text(crlf)


def test_certificate_rejects_a_changed_isolated_analysis_input(tmp_path, monkeypatch):
    """A changed analysis input, not merely a tampered envelope, must invalidate evidence."""
    monkeypatch.setattr(certificate, "INPUT_PATHS", ("fixture_input.txt",))
    (tmp_path / "fixture_input.txt").write_text("original", encoding="utf-8")
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "rigor.py").write_text("# fixture", encoding="utf-8")
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "ADR-0009-analytical-contract.md").write_text("# fixture", encoding="utf-8")
    seed = tmp_path / "dbt" / "seeds"
    seed.mkdir(parents=True)
    (seed / "disruption_dates.csv").write_text(
        "date,source_url\n2024-01-01,https://example.test\n", encoding="utf-8"
    )
    configuration = {
        "random_seed": 42,
        "headline_cluster_bootstrap": {
            "unit": "event_day",
            "replicates": 2000,
            "ci_method": "percentile_95",
        },
        "placebo": {"draws": 1000, "day_of_week_matched": True},
        "event_count": 13,
    }
    evidence = {
        "certificate": certificate.build_certificate(
            tmp_path,
            generated_at="2026-07-23T00:00:00Z",
            journey_coverage={},
            analysis_configuration=configuration,
            certified_result={"headline": {"n_events": 13}, "placebo": {}, "sensitivity": {}},
        ),
        "headline": {"n_events": 13},
        "placebo": {},
        "sensitivity": {},
    }
    certificate.validate_certificate(evidence, tmp_path)
    (tmp_path / "fixture_input.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch: fixture_input.txt"):
        certificate.validate_certificate(evidence, tmp_path)


def test_certificate_rejects_a_tampered_certified_headline():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    evidence["headline"]["median_ratio"] = 9.999
    with pytest.raises(ValueError, match="certified result mismatch"):
        certificate.validate_certificate(evidence, ROOT)


def test_certificate_envelope_locks_seeded_analysis_configuration():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    config = evidence["certificate"]["analysis_configuration"]
    assert config == {
        "random_seed": 42,
        "headline_cluster_bootstrap": {
            "unit": "event_day",
            "replicates": 2000,
            "ci_method": "percentile_95",
        },
        "placebo": {"draws": 1000, "day_of_week_matched": True},
        "event_count": 13,
    }


def test_certified_historical_inputs_exclude_the_forward_event_log():
    assert "app/gold_export/disruption_events.parquet" not in certificate.INPUT_PATHS
    forward_guard = (ROOT / "dbt" / "tests" / "assert_forward_event_log_boundary.sql").read_text(encoding="utf-8")
    assert "2026-07-08" in forward_guard


def test_raw_diagnostics_cannot_produce_a_certified_headline():
    access = (ROOT / "app" / "data_access.py").read_text(encoding="utf-8")
    measures = (ROOT / "powerbi" / "measures.dax").read_text(encoding="utf-8")
    assert "def disruption_headline" not in access
    assert "median(deviation_ratio)" not in access
    assert "Diagnostic Disruption Demand Ratio" not in measures


def test_daily_workflow_regenerates_and_validates_certificate_before_commit():
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert "python analysis/rigor.py" in workflow
    assert "python analysis/certificate.py --verify" in workflow
    assert workflow.index("python analysis/rigor.py") < workflow.index("python analysis/certificate.py --verify")
    assert workflow.index("python analysis/certificate.py --verify") < workflow.index("Commit refreshed data")


def test_powerbi_imports_a_disconnected_certificate_table():
    queries = (ROOT / "powerbi" / "queries.pq").read_text(encoding="utf-8")
    model = (ROOT / "powerbi" / "model.tmdl").read_text(encoding="utf-8")
    measures = (ROOT / "powerbi" / "measures.dax").read_text(encoding="utf-8")
    assert "certified_adr0009_evidence" in queries
    assert "table certified_adr0009_evidence" in model
    relationship_block = model.split("// ─────────────────────────────  Relationships", 1)[1]
    assert "certified_adr0009_evidence." not in relationship_block
    assert "Certified ADR-0009 Demand Ratio" in measures
    assert "MAX ( certified_adr0009_evidence[headline_ratio] )" in measures
    assert "MAX ( certified_adr0009_evidence[permitted_claim] )" in measures
