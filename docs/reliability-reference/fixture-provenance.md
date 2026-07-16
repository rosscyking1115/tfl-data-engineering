# Fixture provenance

The pack contains 14 tiny constructed CSV fixtures with JSON sidecars. Eight are byte-identical
copies of the frozen Gate 0 fixtures; validation recomputes and compares their hashes with
`benchmark/gate0/`. Six additional constructed fixtures cover a new period, malformed duration,
truncation, unknown header, ownership boundary, and DST ambiguity.

Every sidecar records object identity, schema family, exact header fingerprint, ownership period,
expected source-row count, supersession, provenance, publication decision, scenario motivation,
and expected disposition. `fixture_bytes` is always `constructed`. An observed motivation—such as
the locally measured partial boundary date or header drift—does not turn synthetic rows into TfL
source rows.

No fixture was downloaded during T2 and no raw TfL row is published. The authoritative expected
semantic values are the reviewed JSON files under `benchmark/reliability_reference/expected/`.
