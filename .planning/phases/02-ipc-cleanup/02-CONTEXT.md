# Phase 2: IPC Cleanup - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the `os.dup(1)` / `os.dup2(2, 1)` stdout redirect hack in server.py with an explicit `--protocol-fd N` CLI argument. Update ProcessBridge.swift to create a dedicated pipe, pass its fd number as a CLI arg, and read JSON events from that pipe instead of stdout. After this phase, adding log-heavy VAD and Whisper components cannot corrupt the protocol stream.

</domain>

<decisions>
## Implementation Decisions

### Protocol fd approach
- **D-01:** server.py accepts `--protocol-fd N` via argparse. When present, opens that fd with `os.fdopen(N, "w", buffering=1)` for JSON output. When absent (CLI mode), writes JSON to stdout directly. No fd redirect hack in either case.
- **D-02:** The `os.dup(1)` / `os.dup2(2, 1)` hack and all related comments are removed entirely. No backward compat fallback — SwiftUI app and server.py are updated together in this phase.
- **D-03:** Import ordering constraint ("imports after stdout redirect") is eliminated. Imports can happen normally at the top of server.py.

### SwiftUI ProcessBridge
- **D-04:** ProcessBridge.swift creates an extra `Pipe()` for the protocol channel. Passes the write end's fd number as `--protocol-fd {N}` in the process arguments. Reads JSON from the read end instead of stdout.
- **D-05:** stdout remains connected to a pipe for capturing any stray output (logged alongside stderr), but is no longer the protocol channel.

### CLI mode
- **D-06:** `python -m src.server` without `--protocol-fd` writes JSON to stdout. This keeps CLI debugging simple — pipe server output through `jq` or `python -m json.tool`.
- **D-07:** `realtime_demo.py` is not affected — it doesn't use server.py's IPC at all.

### Logging
- **D-08:** Logging stays on stderr with current format. No changes to logging setup needed — removing the dup2 hack simplifies it (no need for special stderr redirect).

### Claude's Discretion
- Print enforcement: Whether to add a grep check for print() in src/ — implementation detail
- Exact argparse setup and error handling for invalid --protocol-fd values
- Whether to add a smoke test validating JSON protocol integrity

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `.planning/research/ARCHITECTURE.md` — Specifies the `--protocol-fd` pattern, code examples, fallback behavior
- `.planning/research/PITFALLS.md` — Pitfall 7 (IPC protocol divergence), Pitfall 14 (print corruption)
- `.planning/research/FEATURES.md` — IPC cleanup rationale and two approaches compared

### Current implementation
- `src/server.py` — Current fd redirect hack (lines 25-27), _send() function, main loop
- `EsperApp/EsperApp/ProcessBridge.swift` — Current stdout-based reading, Pipe setup, launch()
- `EsperApp/EsperApp/TranscriptionEngine.swift` — Consumes ProcessBridge events

### Phase 1 outputs
- `src/config.py` — Config constants (DEFAULT_ENGINE, MODEL_LOAD_TIMEOUT_S) used by server.py

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ProcessBridge.swift`: Already has Pipe creation pattern — adding a protocol pipe is the same pattern
- `server.py _send()`: Already writes to `_proto_out` — just need to change how `_proto_out` is initialized
- `ServerEvent.parse(json:)`: JSON parsing on Swift side doesn't change — same events, different transport

### Established Patterns
- JSON-line protocol: `{"event": "...", "data": {...}}` format stays identical
- AsyncStream for event delivery in Swift — no change needed
- stdin for commands (Swift→Python) — no change needed

### Integration Points
- `ProcessBridge.launch()` — Must add protocol pipe creation and --protocol-fd argument
- `server.py` module level — Must replace os.dup/dup2 with argparse-based fd selection
- `server.py _send()` — Must use new _proto_out source

</code_context>

<specifics>
## Specific Ideas

No specific requirements — user deferred all decisions to Claude for this infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-ipc-cleanup*
*Context gathered: 2026-03-27*
