# Phase 2: IPC Cleanup - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 02-ipc-cleanup
**Areas discussed:** None (user deferred all to Claude)

---

## Gray Area Selection

User was presented with 4 gray areas:
1. Backward compatibility
2. CLI server mode
3. Print enforcement
4. Logging changes

**User's response:** "what is ipc do whatever is best"

User is not familiar with IPC internals and deferred all technical decisions to Claude. All decisions in CONTEXT.md are Claude's discretion based on ARCHITECTURE.md research and codebase analysis.

## Claude's Discretion

- Backward compatibility: Clean break (remove os.dup hack entirely, no fallback)
- CLI mode: No --protocol-fd = stdout mode (simple, debuggable)
- Print enforcement: Left to implementation discretion
- Logging: No changes needed
- SwiftUI Pipe creation: Standard Pipe() pattern, pass write end fd

## Deferred Ideas

None
