# Civil 3D First-Write Test — Synthetic Disposable DWG Protocol

The separately-approved manual test that follows the workstation build (`docs/CIVIL3D_MCP_BUILDOUT.md`). It runs only after the read-only validation gate has passed, and it touches nothing but a synthetic drawing created for this test.

## Authority chain

1. **Build session** completes steps 1–3 of the build guide (plugin NETLOADed, `C3DMCPSTATUS` running, server registered).
2. **Read-only proof** completes on copies (gate steps 2–4): `civil3d_skills` listing, `civil3d_query` results spot-checked against Civil 3D's own reports, sandbox probe confirming a blocked operation is rejected.
3. **Grant**: Joe mints a one-time launch grant on the workstation — `python scripts/trusted_launcher.py grant --mount civil3d --minutes 30` — and launches the mount through `trusted_launcher.py launch`. No grant, no mount: the denial paths are proven by `tests/test_trusted_launcher.py`.
4. **This test** is a *separate* approval from the grant: Joe states, in the session, that the first-write test is authorized before any `civil3d_execute` call is made.

## The synthetic disposable DWG

- In Civil 3D: **New** from the standard C3D template → save as `C3D_MCP_WRITE_TEST.dwg` in a scratch folder outside any project directory.
- The drawing must contain no project content, no client data, no xrefs. It exists to be discarded.

## Test steps (one write, verified, then destroyed)

1. `civil3d_query`: confirm the open document is `C3D_MCP_WRITE_TEST.dwg` and record its object counts. Abort if the active document is anything else.
2. One `civil3d_execute`: create a single line from (0,0) to (100,100) on layer `MCP-TEST`.
3. Readback via `civil3d_query`: confirm exactly one new entity exists, on `MCP-TEST`, with those endpoints — the mutation-verified-by-readback rule.
4. Record the result (pass/fail, timestamps, grant nonce) in the audit ledger and the registry entry.
5. **Destroy**: close without further saves and delete `C3D_MCP_WRITE_TEST.dwg`. The rollback is the file's deletion.

## Hard stops

- Any project DWG open in the session → abort before step 1.
- Readback mismatch → the connector stays `candidate`, failure logged to the error ledger, no second attempt in the same session.
- Grant expiry mid-test → re-approval required; the mount will not relaunch on the consumed grant (single-use is enforced and tested).

Only after this test passes does the registry entry advance past its validation gate, and production-DWG use still requires explicit task-level instruction per the registry boundaries.
