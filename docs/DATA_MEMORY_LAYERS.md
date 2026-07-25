# Data and Memory Layers — llama_index, mem0, crewAI

Runtime record, 2026-07-24. Third build-out wave on the runtime branch, per Joe's directive; all three platforms pre-pinned in the `requirements/` tiers.

## llama_index — governed evidence indexes (implemented)

`scripts/evidence_index.py`. The index `apex_intelligence_forge` was designed for now exists: namespace-scoped indexes for `APEX/Source-Index`, `APEX/Reusable-Playbooks` (writer: apex_intelligence_forge), and `JEOS/Reflection-Ledger` (writer: jeos_reflection_forge). Writes are designated-writer-only and audit-logged; reads are brain-locked (own brain plus Agent 007 — cross-brain retrieval routes through 007). Offline by default: `SimpleKeywordTableIndex` with regex extraction and the simple retriever, LLM pinned to a mock so no key or network is ever touched; semantic `VectorStoreIndex` mode is an activation-time swap inside the same governance wrapper. Retrieval is grounded — "what patterns in my energy over 90 days" answers from indexed entries, not recall.

## mem0 — governed memory gateway on the scope model (implemented; backend activation-gated)

`scripts/memory_layer.py`. mem0's three scopes map onto the governance exactly as directed: manifest namespaces ↔ `agent_id` (the namespace's final segment names its owner), `user_id="joe"` ↔ the cross-brain user scope. The rules are now executable, not prose: **reads open within a brain** (plus 007 across brains; user scope readable by all), **writes leased** — `add()` to a namespace requires the caller to be the namespace owner *and* present an active writer lease that PacketGuard validates and that names the caller. User-scope writes are 007-only. Verify-before-write (the absorbed kody pattern) refuses identical duplicates. The backend is duck-typed: `KeywordMemoryBackend` (stdlib JSON + token search) runs the governance offline today; `mem0.Memory` drops in at activation unchanged — mem0 itself needs an LLM for fact extraction, so it is activation-gated.

## crewAI — the roster as role-based crews (implemented; kickoff activation-gated)

`scripts/crew_bridge.py`. The near-1:1 mapping Joe identified, executed: TOML definitions → `Agent(role, goal, backstory)`; delegation packets → `Task(description, expected_output, agent)` with `required_artifact_types` and definition-of-done IDs composing the expected output; the mirrored class structure → two single-brain crews with Agent 007 as the integration step outside both. Governance preserved: every task enters a crew only through the same fail-closed `admit_delegation()`; a crew is single-brain by construction (mixed-brain packets raise); crewAI's built-in delegation stays enabled *within* a crew, which is exactly the community protocol's same-brain collaboration rule. `Crew.kickoff()` (live execution) is activation-gated and never called by the bridge.

## Validation

Stdlib: full suite green, heavy-dependency tests skip by design. Pinned venv (`llama-index-core 0.14.23`, `mem0ai`, `crewai 0.193.2` added): all data/memory-layer tests pass — leased writes, brain-locked reads, writer locks, fail-closed crew admission.

## Boundaries and rollback

No credentials stored or read; live paths (vector embeddings, mem0 managed backend, crew kickoff) activate only on Joe's instruction under the shadow-stage gates. Rollback: delete `scripts/evidence_index.py`, `scripts/memory_layer.py`, `scripts/crew_bridge.py`, `tests/test_data_memory_layers.py`, and this document.
