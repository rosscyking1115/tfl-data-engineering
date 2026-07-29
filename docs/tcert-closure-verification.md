# T-CERT closure verification

The certificate is the exclusive owner of the ADR-0009 historical headline. This
record covers the final closure checks without rebuilding external dbt models or
changing committed Parquet snapshots.

The envelope canonically hashes the result-bearing `headline`, `placebo`, and
`sensitivity` payload and incorporates that digest into the certificate ID. A
changed headline or uncertainty value therefore fails validation even when its
analysis inputs and configuration have not changed. Per-event and spatial views
remain diagnostics, outside the historical headline certificate.

## Commands and results — 2026-07-23

```powershell
.\.venv\Scripts\python.exe analysis\rigor.py
.\.venv\Scripts\python.exe analysis\certificate.py --verify app\gold_export\analysis_rigor.json
```

Exit code: `0`.

```text
headline: 1.423x  (95% CI 1.241-1.608)  over 13 events
placebo:  null median 1.0  null 97.5th 1.089  p(one-sided) < 0.001
baselines: median 1.423 vs ML 1.298
wrote app/gold_export/analysis_rigor.json
[OK] certified evidence: app\gold_export\analysis_rigor.json
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_tcert.py tests\test_data_access.py tests\test_quick_answers.py tests\test_assistant.py tests\test_consumer_operations_polish.py -q
.\.venv\Scripts\python.exe -m ruff check analysis app tests
git diff --check
```

Exit code: `0`.

```text
.............................                                            [100%]
All checks passed!
```

```powershell
.\.venv\Scripts\dbt.exe build --target duckdb --project-dir dbt --profiles-dir dbt --select certified_adr0009_evidence
.\.venv\Scripts\dbt.exe test --target duckdb --project-dir dbt --profiles-dir dbt --select assert_deviation_ratio_requires_positive_expected assert_strike_seed_has_citations assert_forward_event_log_boundary
```

Exit code: `0`. The selection is limited to the certificate view and three
read-only singular guards; it does not select dbt external materialisations.
`git status --short` immediately afterwards showed no changed Parquet files.

## Power BI delivery status

Completed (2026-07-24). Power BI Desktop loaded the local certified semantic
model and its certificate table. The Desktop validation query returned the
same 1.423 headline ratio without filters, under a date slice, and under a
station slice; its 95% confidence interval was 1.241–1.608. That confirms the
certificate table is disconnected from the date and station dimensions and
that Power BI consumes the rigor-owned evidence rather than deriving a second
headline.

### The closure review, and what a reader here cannot check

Closure was signed off **PASS** by a Reviewer/QA pass on 2026-07-24. That record
(`2026-07-24-tfl-tcert-powerbi-closure.md`) is an internal governance file kept
outside this repository and **is not published**, so the sign-off itself cannot be
verified by anyone reading this repo. Its substantive findings are summarised
below so the claim rests on something checkable against the code, rather than on a
pointer no reader can follow:

- `analysis/rigor.py` is the only producer of the result; `analysis/certificate.py`
  validates provenance and derives no uplift, interval or comparator.
- **No second ADR-0009 uplift calculation was found anywhere in the repository.**
  That is the finding that matters most here, and it is the one you can re-check
  yourself — the consumers are `dbt/models/analytics/certified_adr0009_evidence.sql`,
  `app/data_access.py`, `app/assistant.py` and `powerbi/measures.dax`.
- dbt's `certified_adr0009_evidence` is a thin `read_json_auto` view over the same
  JSON that Streamlit and the assistant read.
- The packaged `.pbit` semantic model imports the certificate table, exposes only
  certificate-consuming `MAX` measures, and contains **no relationship involving
  that table** — the structural reason date and station slicers cannot filter it.
- Fresh consumer tests (29 passing in the selected set at that date), `ruff`, and
  `git diff --check` were clean, and no Parquet or committed snapshot changed.

Two limits the review recorded explicitly, which this document should not soften:

- The PASS covers the **delivered template, queries and semantic model** — not a
  pre-designed report. The report canvas contains no pre-built visual containers.
- The Desktop open-and-query sequence was performed by the repository owner, and
  Reviewer/QA **did not repeat it**. That step is owner-verified, not independently
  reproduced.
