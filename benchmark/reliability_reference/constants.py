"""Repository paths and immutable contract constants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
FIXTURE_ROOT = ROOT / "fixtures"
SCENARIO_ROOT = ROOT / "scenarios"
EXPECTED_ROOT = ROOT / "expected"
CONTRACT_ROOT = ROOT / "contracts"
GATE0_FIXTURE_ROOT = REPO_ROOT / "benchmark" / "gate0" / "fixtures"
SCHEMA_MAP_PATH = CONTRACT_ROOT / "schema-map.json"

VERSION = "0.2.0"
CONTRACT_VERSION = "1"
EMPTY_STATE_HASH = "sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
MANAGED_SCENARIOS = (
    "001_initial_variants",
    "002_duplicate_replay",
    "003_new_period",
    "004_corrected_period",
    "008_interrupted_publish",
    "009_full_rebuild",
    "011_incompatible_replacement",
)
