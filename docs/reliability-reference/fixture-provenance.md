# Fixture provenance

The pack contains 16 tiny constructed CSV fixtures with JSON sidecars. Eight are byte-identical
copies of the frozen Gate 0 fixtures; validation recomputes and compares their hashes with
`benchmark/gate0/`. Eight additional constructed fixtures cover a new period, malformed duration,
truncation, unknown header, overlapping ownership, state-wide duplicate identity, an ownership
boundary, and DST ambiguity.

Every sidecar records the object identity, schema family, exact header fingerprint, ownership
period, expected source-row count, supersession, provenance, publication decision, scenario
motivation and expected disposition. `fixture_kind` is always `constructed`. An observed
motivation, such as the locally measured partial boundary date or header drift, does not turn
synthetic rows into TfL source rows.

No fixture was downloaded during T2 and no raw TfL row is published. The authoritative expected
semantic values are the reviewed JSON files under `benchmark/reliability_reference/expected/`.
