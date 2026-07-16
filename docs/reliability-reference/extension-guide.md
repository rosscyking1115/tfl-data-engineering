# Extension guide

An extension must add evidence before adding acceptance surface. Record whether the motivating
condition is observed, derived, or constructed; never infer raw provenance from a matching header.

To add a header variant, first verify its exact ordered fingerprint against retained evidence, then
extend the JSON mapping, add a minimal constructed fixture and complete sidecar, add reviewed JSON
oracle output, and require both native adapters to match it. Unknown or reordered headers remain
whole-object rejections until that review is complete.

To add a state transition, define ownership and expected disposition in JSON, demonstrate pointer
preservation on every failure path, demonstrate retry equivalence with a clean rebuild, and update
the cross-engine comparison. Engine-specific normalization stays inside its adapter; shared code may
own validation and state transitions but must not become a shared row transformer.
