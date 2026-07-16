# Standards and managed feasibility

Checked: **2026-07-16 UTC**.

## Standards decisions

| candidate | decision | Gate 0 reason |
|---|---|---|
| [Open Data Contract Standard 3.1](https://github.com/bitol-io/open-data-contract-standard) | considered, not selected | Useful if this becomes a portable published dataset contract in T2; Gate 0's JSON mapping and replay semantics are smaller and directly executable. |
| [dbt model contracts](https://docs.getdbt.com/docs/mesh/govern/model-contracts) | considered, not selected | dbt recommends contracts for public models relied on downstream. Gate 0 exposes fixtures and a Python seam, not a new public dbt model. |
| [DuckLake](https://ducklake.select/) | considered, not selected | The spike needs atomic in-memory replacement semantics and hashes, not a durable multi-table catalog. Adding DuckLake would not satisfy a measured unmet requirement. |
| [OpenLineage](https://openlineage.io/docs/) | considered, not selected | Static fixtures have deterministic provenance sidecars. Emitting lineage events would add plumbing without strengthening an asserted invariant. |

ODCS and dbt contracts may be revisited only for a public T2 dataset or downstream model. DuckLake
or OpenLineage requires a demonstrated requirement and a measurable before/after result.

## Databricks validate-only lane

The committed Declarative Automation Bundle skeleton is under `benchmark/gate0/managed/`.
No Databricks CLI or local profile was present on 2026-07-16. Therefore neither
`databricks bundle schema` nor authenticated `databricks bundle validate` was run.

**Result: `NARROW — unverified`.** This does not fail the portable contribution. No workspace
identity was recorded, and no deploy, run, table creation, teardown, or other remote API action
occurred. The observation is retained in [managed-validation.json](managed-validation.json).

The official Free Edition documentation says it is serverless-only, fair-usage/quota limited,
non-commercial, and has no guaranteed reliability, support, or SLA. It currently limits jobs to
five concurrent tasks. These limits make it a demonstration target, not an authority for the
portable oracle. See [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)
and the [bundle command reference](https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands).

## Revisit gate

Managed validation may move out of `NARROW` only when an existing authorized profile is available,
the CLI identity is redacted from evidence, `bundle schema` and `bundle validate` pass, and the
operator confirms that no mutating command is run. Deployment remains outside T1.
