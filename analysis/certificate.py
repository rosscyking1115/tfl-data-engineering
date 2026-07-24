"""Certificate contract for the locked ADR-0009 rigor export.

This module validates provenance around an already-computed result.  It must never
derive the uplift, confidence interval, or comparator values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "1.0"
ADR_ID = "ADR-0009"
CLAIM_CLASS = "observed_association"
PERMITTED_CLAIM = (
    "On days with a verified, source-cited London Underground strike, Santander cycle-hire "
    "demand runs at a median 1.42× its weather-adjusted expectation. This is an observed "
    "association, not a causal effect."
)
INPUT_PATHS = (
    "app/gold_export/demand_deviation.parquet",
    "app/gold_export/demand_deviation_ml.parquet",
    "app/gold_export/station_daily_flows.parquet",
    "app/gold_export/weather_daily.parquet",
    "dbt/seeds/disruption_dates.csv",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_hashes(root: Path) -> dict[str, str]:
    return {relative: sha256_file(root / relative) for relative in INPUT_PATHS}


def certified_result_payload(evidence: dict) -> dict:
    """Return the ADR-0009 result-bearing fields guarded by the certificate.

    Spatial and per-event views are diagnostics, not the certified historical
    headline.  The headline, placebo and sensitivity evidence are therefore the
    bounded result payload: changing any of them invalidates the certificate.
    """
    return {
        "headline": evidence.get("headline"),
        "placebo": evidence.get("placebo"),
        "sensitivity": evidence.get("sensitivity"),
    }


def certified_result_sha256(evidence: dict) -> str:
    material = json.dumps(certified_result_payload(evidence), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _certificate_id(
    input_sha256: dict[str, str], code_sha256: str, analysis_configuration: dict, result_sha256: str
) -> str:
    material = json.dumps(
        {
            "inputs": input_sha256,
            "code": code_sha256,
            "analysis_configuration": analysis_configuration,
            "certified_result_sha256": result_sha256,
        },
        sort_keys=True,
    )
    return f"tcert-adr0009-{hashlib.sha256(material.encode()).hexdigest()[:12]}"


def build_certificate(
    root: Path, *, generated_at: str, journey_coverage: dict, analysis_configuration: dict, certified_result: dict
) -> dict:
    """Build provenance for the existing rigor result without calculating it."""
    hashes = input_hashes(root)
    code_sha256 = sha256_file(root / "analysis" / "rigor.py")
    result_sha256 = certified_result_sha256(certified_result)
    return {
        "certificate_schema_version": SCHEMA_VERSION,
        "evidence_version": "tcert-adr0009-v1",
        "certificate_id": _certificate_id(hashes, code_sha256, analysis_configuration, result_sha256),
        "adr_id": ADR_ID,
        "adr_document_sha256": sha256_file(root / "docs" / "adr" / "ADR-0009-analytical-contract.md"),
        "generated_at_utc": generated_at,
        "claim_class": CLAIM_CLASS,
        "permitted_claim": PERMITTED_CLAIM,
        "primary_specification": {
            "grain": "station × day",
            "statistic": "median station-day actual / expected",
            "min_expected_departures": 5,
            "comparator_family": "stratified_median",
            "counterfactual_families": ["stratified_median", "lightgbm_counterfactual"],
            "weather_thresholds": {"wet_mm": 1.0, "cold_c": 8.0},
            "strike_seed": "dbt/seeds/disruption_dates.csv",
            "seed_requires_source_url": True,
        },
        "journey_coverage": journey_coverage,
        "analysis_configuration": analysis_configuration,
        "certified_result_sha256": result_sha256,
        "input_sha256": hashes,
        "code_sha256": code_sha256,
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_certificate(evidence: dict, root: Path) -> None:
    """Reject stale, incomplete, or contract-drifting evidence exports."""
    certificate = evidence.get("certificate")
    _require(isinstance(certificate, dict), "missing certificate envelope")
    _require(certificate.get("certificate_schema_version") == SCHEMA_VERSION, "certificate schema mismatch")
    _require(certificate.get("adr_id") == ADR_ID, "ADR mismatch")
    _require(certificate.get("claim_class") == CLAIM_CLASS, "claim class mismatch")
    _require(certificate.get("permitted_claim") == PERMITTED_CLAIM, "permitted claim mismatch")
    spec = certificate.get("primary_specification", {})
    _require(spec.get("grain") == "station × day", "grain mismatch")
    _require(spec.get("statistic") == "median station-day actual / expected", "statistic mismatch")
    _require(spec.get("min_expected_departures") == 5, "eligibility mismatch")
    _require(spec.get("strike_seed") == "dbt/seeds/disruption_dates.csv", "strike seed mismatch")
    _require(set(spec.get("counterfactual_families", [])) == {"stratified_median", "lightgbm_counterfactual"}, "comparator-family mismatch")
    _require(isinstance(certificate.get("journey_coverage"), dict), "missing journey coverage")
    _require(isinstance(evidence.get("headline"), dict), "missing uncertainty-bearing headline")
    _require(isinstance(evidence.get("placebo"), dict), "missing placebo evidence")
    _require(isinstance(evidence.get("sensitivity"), dict), "missing sensitivity evidence")
    expected_configuration = {
        "random_seed": 42,
        "headline_cluster_bootstrap": {
            "unit": "event_day",
            "replicates": 2000,
            "ci_method": "percentile_95",
        },
        "placebo": {"draws": 1000, "day_of_week_matched": True},
        "event_count": evidence["headline"].get("n_events"),
    }
    _require(certificate.get("analysis_configuration") == expected_configuration, "analysis configuration mismatch")
    result_sha256 = certified_result_sha256(evidence)
    _require(certificate.get("certified_result_sha256") == result_sha256, "certified result mismatch")

    expected_inputs = input_hashes(root)
    recorded_inputs = certificate.get("input_sha256", {})
    for relative, digest in expected_inputs.items():
        _require(recorded_inputs.get(relative) == digest, f"hash mismatch: {relative}")
    _require(certificate.get("code_sha256") == sha256_file(root / "analysis" / "rigor.py"), "hash mismatch: analysis/rigor.py")
    _require(certificate.get("adr_document_sha256") == sha256_file(root / "docs" / "adr" / "ADR-0009-analytical-contract.md"), "hash mismatch: ADR-0009")
    _require(
        certificate.get("certificate_id")
        == _certificate_id(recorded_inputs, certificate["code_sha256"], expected_configuration, result_sha256),
        "certificate ID mismatch",
    )

    with (root / "dbt" / "seeds" / "disruption_dates.csv").open(encoding="utf-8", newline="") as seed_file:
        rows = list(csv.DictReader(seed_file))
    _require(bool(rows) and all(row.get("source_url", "").strip() for row in rows), "strike-seed provenance missing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    validate_certificate(json.loads(args.verify.read_text(encoding="utf-8")), root)
    print(f"[OK] certified evidence: {args.verify}")


if __name__ == "__main__":
    main()
