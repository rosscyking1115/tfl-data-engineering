import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts.build_reliability_release import T2_COMMIT, ReleaseError, validate_release_policy

ROOT = Path(__file__).parents[1]
RELEASE_DOCS = ROOT / "docs" / "reliability-reference" / "releases" / "0.3.0"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def test_fallback_release_policy_is_pinned_to_frozen_t2():
    validate_release_policy("0.2.0", "NARROW", T2_COMMIT)

    with pytest.raises(ReleaseError, match="T2 commit"):
        validate_release_policy("0.2.0", "NARROW", "HEAD")
    with pytest.raises(ReleaseError, match="managed PASS"):
        validate_release_policy("0.3.0", "NARROW", "HEAD")
    with pytest.raises(ReleaseError, match="STOP"):
        validate_release_policy("0.2.0", "STOP", T2_COMMIT)


def test_terminal_narrow_report_is_redacted_hashed_and_torn_down():
    evidence = json.loads((RELEASE_DOCS / "managed-proof.json").read_text(encoding="utf-8"))

    assert evidence["result"] == "NARROW"
    assert evidence["managed_attempts"] == 0
    assert evidence["managed_invocations"] == 3
    assert evidence["corrective_redeploys"] == 1
    assert evidence["scenario_results"] == []
    assert evidence["portable_comparison"] is None
    assert COMMIT.fullmatch(evidence["candidate_commit"])
    for field in (
        "bundle_hash",
        "fixture_manifest_hash",
        "claim_ledger_hash",
        "candidate_tree_hash",
    ):
        assert SHA256.fullmatch(evidence[field])
    assert evidence["claim_ledger_hash"] == hashlib.sha256(
        (RELEASE_DOCS / "claim-ledger.json").read_bytes()
    ).hexdigest()
    assert evidence["teardown"]["verified"] is True
    assert all(
        evidence["teardown"][field] is True
        for field in (
            "job_absent",
            "schema_absent",
            "volume_absent",
            "tables_absent",
            "bundle_artifacts_absent",
        )
    )
    rendered = json.dumps(evidence)
    assert "@" not in rendered
    assert ".cloud.databricks.com" not in rendered
    assert "dapi" not in rendered


def test_narrow_visuals_are_identity_safe_and_do_not_claim_delta_pass():
    for name in ("portable-managed-recovery.svg", "conformance-matrix.svg"):
        svg = (RELEASE_DOCS / name).read_text(encoding="utf-8")
        assert "<title" in svg and "<desc" in svg
        assert "NARROW" in svg
        assert "@" not in svg and ".cloud.databricks.com" not in svg
    matrix = (RELEASE_DOCS / "conformance-matrix.svg").read_text(encoding="utf-8")
    assert "Oracle not reached" in matrix


def test_manual_release_workflow_is_fixed_to_the_narrow_fallback():
    workflow = (ROOT / ".github" / "workflows" / "reliability-release.yml").read_text(
        encoding="utf-8"
    )

    assert 'OWNER_APPROVAL: ${{ inputs.owner_approval }}' in workflow
    assert '--version "0.2.0"' in workflow
    assert '--managed-result "NARROW"' in workflow
    assert f'--target "{T2_COMMIT}"' in workflow
    assert 'gh release create "v0.2.0"' in workflow
    assert "v0.3.0" not in workflow
