# Extension guide

An extension starts with evidence. Record whether its motivation is observed, derived or
constructed. A matching header does not establish raw-source provenance.

To add a header variant, verify its exact ordered fingerprint against retained evidence. Then
extend the JSON mapping, add a minimal constructed fixture with a complete sidecar, record the
reviewed JSON oracle output and require both native adapters to match it. Unknown or reordered
headers remain whole-object rejections until the review is complete.

To add a state transition, define ownership and expected disposition in JSON. Show that every
failure path preserves the pointer, that retry matches a clean rebuild and that both engines agree.
Engine-specific normalisation stays inside its adapter. Shared code may own validation and state
transitions, but it must not transform rows for both engines.
