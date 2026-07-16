"""Non-deployed placeholder referenced by the validate-only bundle skeleton."""

from pathlib import Path


def main() -> None:
    gate0_root = Path(__file__).parents[1]
    expected = gate0_root / "expected" / "normalize-five-variants.json"
    if not expected.is_file():
        raise SystemExit(f"missing portable expected output: {expected}")
    print("Gate 0 portable artifacts are present; no managed resources were created.")


if __name__ == "__main__":
    main()
