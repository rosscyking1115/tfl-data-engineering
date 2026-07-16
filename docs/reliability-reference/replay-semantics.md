# Replay and recovery semantics

Each run stages data under `staging/<run_id>`, validates the complete source object, writes an
immutable `states/<version>` directory, and atomically replaces `current.json` only after the new
state is durable. A failed run retains its run evidence and leaves the prior pointer and state
unchanged.

An exact content-hash replay is a no-op. A correction must name an active object and use its exact
inclusive ownership period; only after full validation does it replace every row in that period.
An incompatible correction, invalid object, ambiguous timestamp, or injected interruption cannot
change the visible state. Retrying each of the three interruption hooks produces the same state as
an uninterrupted run and a clean rebuild.

State directories are immutable protocol artifacts. The runner performs no implicit garbage
collection. Workspace deletion or retention is a separate, explicit caller decision so recovery
evidence cannot disappear as a side effect of ingestion.
