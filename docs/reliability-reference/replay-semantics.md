# Replay and recovery semantics

Each run stages data under `staging/<run_id>`, validates the complete source object, writes an
immutable `states/<version>` directory and atomically replaces `current.json` only after the new
state is durable. A failed run retains its run evidence and leaves the prior pointer and state
unchanged.

An exact content-hash replay is a no-op. A correction must name an active object and use its exact
inclusive ownership period; only after full validation does it replace every row in that period.
A non-correction object whose inclusive ownership period overlaps any active object is rejected.
Every candidate state is also checked for unique `(schema_family, rental_id)` identities before it
can be staged. An incompatible correction, invalid object, ambiguous timestamp, ownership overlap,
duplicate identity or injected interruption cannot change the visible state. Retrying any of the
three interruption hooks produces the same state as an uninterrupted run and a clean rebuild in
both DuckDB and Spark.

State directories are immutable protocol artifacts. The runner performs no implicit garbage
collection. Workspace deletion or retention is a separate, explicit caller decision so recovery
evidence cannot disappear as a side effect of ingestion.
