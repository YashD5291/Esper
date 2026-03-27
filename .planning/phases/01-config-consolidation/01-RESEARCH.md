# Phase 1: Config Consolidation - Research

**Researched:** 2026-03-27
**Domain:** Python module-level constants, runtime mutation, config layering, logging hygiene
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ARCH-01 | Single config.py replaces .env + @AppStorage + CLI args as source of truth | Full: all constant locations inventoried, mutation pattern documented, migration path for each source mapped |
</phase_requirements>

---

## Summary

Phase 1 is a pure code reorganization — no new dependencies, no new features. The codebase currently has config scattered across three sources: a `.env` file (Telegram credentials), module-level constants spread across `audio_capture.py` and `transcriber.py` (SAMPLE_RATE, CHUNK_DURATION, etc.), and hardcoded literals in `server.py` (`_MODEL_LOAD_TIMEOUT = 30`) and `telegram_sender.py` (`_DRAFT_INTERVAL`, `_MAX_RETRIES`). The SwiftUI app passes runtime values via the `start` command JSON payload, which already works correctly and does not need to change — those values flow in at runtime and should be applied to config at that point.

The goal is a single `src/config.py` that every component imports. Three outcomes are required: (1) all tunable constants live in config.py with documented defaults, (2) `audio_capture.py`'s `print()` call on line 75 is replaced with a `log.info()` call (it is a live IPC-corruption landmine per Pitfall 14), and (3) `realtime_demo.py` stops reading from `.env` at import time and instead populates config from the parsed `argparse` namespace at startup.

**Primary recommendation:** Create `src/config.py` with four namespaced sections (AUDIO, VAD, WHISPER, TELEGRAM, IPC), migrate constants from their current homes in a single commit, replace the one dangerous `print()` in `audio_capture.py`, and update the two callers (`server.py` and `realtime_demo.py`) to mutate config at startup rather than passing values deep as constructor arguments.

---

## Current Config Inventory

This is the complete map of every tunable value and where it currently lives. The planner must touch each item.

### Constants in `src/audio_capture.py`

| Constant | Value | Move to config.py? |
|----------|-------|--------------------|
| `SAMPLE_RATE` | `16000` | Yes — imported by `transcriber.py`, `coreml_transcriber.py`, `server.py`, `realtime_demo.py` |
| `CHANNELS` | `1` | Yes |
| `CHUNK_DURATION` | `0.1` (seconds) | Yes — determines `CHUNK_SAMPLES`, currently 1600 samples (100ms blocks). Note: Phase 3 will change `blocksize` to 512 for VAD. Phase 1 just moves this constant; do not change the value yet. |
| `CHUNK_SAMPLES` | `int(SAMPLE_RATE * CHUNK_DURATION)` | Derived — compute in config.py or keep local in audio_capture.py as a derived constant |
| `QUEUE_MAXSIZE` | `300` | Yes |

### Constants in `src/telegram_sender.py`

| Constant | Value | Move to config.py? |
|----------|-------|--------------------|
| `_MAX_RETRIES` | `3` | Yes |
| `_BACKOFF_BASE` | `1.0` | Yes |
| `_DRAFT_INTERVAL` | `0.5` | Yes |

### Constants in `src/server.py`

| Constant | Value | Move to config.py? |
|----------|-------|--------------------|
| `_MODEL_LOAD_TIMEOUT` | `30` | Yes — and update value to `120` per CLEAN-03 requirement (Whisper cold compile takes 45-90s, documented in STATE.md) |
| `_engine_name` default | `"coreml"` | Yes — default engine |

### Telegram credentials in `.env`

| Key | Current source | New source |
|-----|---------------|------------|
| `TELEGRAM_BOT_TOKEN` | `.env` file, read via `python-dotenv` in `realtime_demo.py` | CLI: parsed from `argparse` (or keep `.env` as input to argparse `--telegram-token` arg, or keep `load_dotenv()` in `realtime_demo.py` only — see decision below) |
| `TELEGRAM_CHAT_ID` | `.env` file | Same as above |

**Key decision on Telegram credentials for CLI mode:** The success criteria say "Telegram credentials are passed via the `start` command data dict at runtime, not read from a .env file at import time." This applies to `server.py` (SwiftUI mode). In `realtime_demo.py` (CLI mode), `load_dotenv()` is called inside `if args.telegram:` — this is already lazy (not at import time). The cleanest approach for Phase 1: keep `load_dotenv()` in `realtime_demo.py` (CLI convenience), but have it write to `config.TELEGRAM_BOT_TOKEN` and `config.TELEGRAM_CHAT_ID` rather than using `os.environ` directly. This satisfies "no .env file can override a config constant without going through config.py."

### Future-phase namespaces to stub in config.py now

Per success criterion 4, these must be present in config.py with documented defaults even though Phase 1 does not implement the features:

| Namespace | Constants |
|-----------|-----------|
| VAD | `VAD_FRAME_SIZE = 512`, `VAD_SPEECH_THRESHOLD = 0.5`, `VAD_SILENCE_THRESHOLD_MS = 500`, `VAD_MIN_SPEECH_DURATION_MS = 500`, `VAD_MIN_ENERGY = 0.01` |
| WHISPER | `WHISPER_MODEL_REPO = "mlx-community/whisper-large-v3-turbo"`, `WHISPER_LANGUAGE = "en"`, `WHISPER_MAX_GENERATIONS_BEFORE_RESTART = 50`, `WHISPER_SUBPROCESS_TIMEOUT_S = 15.0` |
| IPC | `ENERGY_EMIT_INTERVAL_S = 0.1` |

---

## Architecture Patterns

### Pattern 1: Module-Level Constants with Runtime Mutation

Python modules are imported once and cached. A `config.py` module with top-level names is effectively a mutable global namespace — any code that does `import config; config.X = value` mutates the shared state seen by all subsequent importers.

**What:** Define all constants as top-level names in `src/config.py`. At startup (in `main()` of `server.py` or `realtime_demo.py`), mutate config values from the incoming data source (JSON payload or argparse). All other modules import config at module level and read values when they need them — not at `__init__` time.

**Example:**
```python
# src/config.py
SAMPLE_RATE: int = 16000
TELEGRAM_BOT_TOKEN: str = ""
TELEGRAM_CHAT_ID: str = ""

# src/server.py — in _do_start(data)
import src.config as config
config.TELEGRAM_BOT_TOKEN = telegram_cfg.get("bot_token", "")
config.TELEGRAM_CHAT_ID = telegram_cfg.get("chat_id", "")

# src/telegram_sender.py — reads from config at construction time
from . import config
class TelegramSender:
    def __init__(self):
        self._base_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
```

**Confidence:** HIGH — standard Python pattern, no external library needed.

### Pattern 2: Import config, Don't Pass Everything as Constructor Args

The current `TelegramSender(bot_token, chat_id)` takes credentials as constructor args because there was no shared config. After Phase 1, `TelegramSender.__init__` can read from config directly. However, the constructor signature must remain backward-compatible for `server.py` which passes them explicitly, OR `server.py` sets `config.TELEGRAM_BOT_TOKEN` before constructing `TelegramSender`. Both work; the latter is cleaner.

**Recommendation:** Keep `TelegramSender.__init__(self, bot_token, chat_id, *, stream=True)` signature unchanged for Phase 1. `server.py` already passes these correctly. The signature cleanup can happen in Phase 5 (Telegram Hardening) when the full contract is redesigned. Phase 1 only needs to move the *internal* constants (`_MAX_RETRIES`, `_BACKOFF_BASE`, `_DRAFT_INTERVAL`) to config.

### Pattern 3: `list_devices()` print() → log()

`audio_capture.py` has two call sites of `print()` that must become `log.info()`:

- Line 22: `print("\nAvailable audio input devices:")` — in `list_devices()` (standalone CLI utility). This one can stay as `print()` because `list_devices()` is only called from `realtime_demo.py` (CLI mode), never from `server.py`. But converting to `log.info()` is consistent.
- **Line 75: `print(f"  Device: [{dev_idx}] {dev_name}")`** — in `AudioCapture.start()`. This is the live landmine. `AudioCapture.start()` is called by `server.py`. Even though `server.py` redirects stdout before importing, the redirect must happen before `AudioCapture.start()` is *called* (not just imported). It does — but the print is one layer away from corrupting IPC. Convert to `log.info()`.

### Pattern 4: Derived Constants

`CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)` is derived from two other constants. In `config.py`, compute it as a derived constant. This keeps the computation in one place and prevents drift:

```python
# src/config.py
SAMPLE_RATE: int = 16000
CHUNK_DURATION: float = 0.1  # seconds
CHUNK_SAMPLES: int = int(SAMPLE_RATE * CHUNK_DURATION)  # 1600 at default settings
```

`audio_capture.py` can then remove the duplicate computation and just `from . import config`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Config file parsing | Custom .ini/.yaml parser | Python module-level constants | Zero dependencies, native Python import caching handles singleton semantics |
| Config validation | Schema validation library | Explicit assertion in `_do_start` | The data dict from SwiftUI is small and fixed; one `assert` block is sufficient |
| Runtime override system | Layered config class with merge logic | Direct attribute mutation on the config module | Single-level override (startup sets values once) is all that's needed here |

**Key insight:** The temptation is to introduce a config library (dynaconf, pydantic-settings, etc.) for "proper" config management. For this codebase — a single-user local app with five parameters — a plain Python module is the correct tool. It has no serialization overhead, no schema files to maintain, and zero new dependencies.

---

## Common Pitfalls

### Pitfall A: Importing SAMPLE_RATE from audio_capture.py after moving it to config.py

**What goes wrong:** `transcriber.py`, `coreml_transcriber.py`, `server.py`, and `realtime_demo.py` all import `SAMPLE_RATE` from `audio_capture.py` via `from .audio_capture import SAMPLE_RATE`. If you move `SAMPLE_RATE` to `config.py` but forget to re-export it from `audio_capture.py` (for backward compat), existing imports break.

**How to avoid:** Two safe options:
1. Move `SAMPLE_RATE` to `config.py` and update every import site simultaneously in one commit.
2. Keep `SAMPLE_RATE` re-exported from `audio_capture.py`: `from . import config; SAMPLE_RATE = config.SAMPLE_RATE` — allows phased migration.

Option 1 is cleaner and Phase 1 touches these files anyway.

**Warning signs:** `ImportError: cannot import name 'SAMPLE_RATE' from 'src.audio_capture'` on any existing import site.

### Pitfall B: Mutating config module before imports complete (circular import)

**What goes wrong:** If `server.py` tries to mutate `config.TELEGRAM_BOT_TOKEN` at module level (outside any function), and `config.py` imports from `server.py` (even transitively), you get a circular import.

**How to avoid:** Keep config.py dependency-free — it imports nothing from `src/`. All mutation happens inside functions (`_do_start`, `main()`), never at module level in `server.py`.

**Warning signs:** `ImportError: partially initialized module 'src.config'` or `ImportError: cannot import name X from partially initialized module`.

### Pitfall C: `list_devices()` function becomes a logging call but the output disappears

**What goes wrong:** `audio_capture.list_devices()` is used in `realtime_demo.py --list-devices` to print device info to the user. If converted to `log.info()`, it only appears when `logging.INFO` is active. In production server mode, logging goes to stderr — fine. But in CLI mode, the user's terminal might not show `INFO` logs if the default level is `WARNING`.

**How to avoid:** In `realtime_demo.py`, the CLI mode explicitly configures `logging.basicConfig(level=logging.DEBUG)` (or use `print()` only in `realtime_demo.py` where it's intentional CLI output). The `list_devices()` function in `audio_capture.py` should convert to `log.info()`. `realtime_demo.py` ensures its logging config enables INFO before calling it.

### Pitfall D: `_MODEL_LOAD_TIMEOUT` change is load-bearing for current CoreML behavior

**What goes wrong:** Changing `_MODEL_LOAD_TIMEOUT` from `30` to `120` means the SwiftUI UI will appear frozen for up to 120s if a model hangs silently. For the current CoreML path (which loads fast), this makes a hung model much harder to detect.

**How to avoid:** The `CLEAN-03` requirement (Phase 4) says to update the timeout to 120s for Whisper cold Metal compile. Strictly, `_MODEL_LOAD_TIMEOUT` exists only in `server.py`, not as a constant imported by other modules. It's fine to move it to config.py now with value `120`. The current CoreML transcriber still loads faster than 30s, so the 120s ceiling is just a safety net. This is the correct value per the existing research (PITFALLS.md Pitfall 10).

---

## Code Examples

### config.py structure
```python
# src/config.py
"""Single source of truth for all Esper tunables.

Every component imports from here. Mutation happens only at startup
(in server._do_start or realtime_demo.main) before any component is
constructed.
"""

# ── Audio ─────────────────────────────────────────────────────────
SAMPLE_RATE: int = 16000
CHANNELS: int = 1
CHUNK_DURATION: float = 0.1            # seconds per sounddevice callback chunk
CHUNK_SAMPLES: int = int(SAMPLE_RATE * CHUNK_DURATION)  # 1600 samples
QUEUE_MAXSIZE: int = 300               # ~30s of buffered audio

# ── VAD (Phase 3) ─────────────────────────────────────────────────
VAD_FRAME_SIZE: int = 512              # samples at 16kHz = 32ms (hard Silero requirement)
VAD_SPEECH_THRESHOLD: float = 0.5     # probability above which frame is speech
VAD_SILENCE_THRESHOLD_MS: int = 500   # ms of silence to seal an utterance
VAD_MIN_SPEECH_DURATION_MS: int = 500 # discard utterances shorter than this
VAD_MIN_ENERGY: float = 0.01          # RMS floor; discard very quiet frames

# ── Whisper (Phase 4) ─────────────────────────────────────────────
WHISPER_MODEL_REPO: str = "mlx-community/whisper-large-v3-turbo"
WHISPER_LANGUAGE: str = "en"
WHISPER_MAX_GENERATIONS_BEFORE_RESTART: int = 50
WHISPER_SUBPROCESS_TIMEOUT_S: float = 15.0

# ── Telegram (set at runtime via start command / CLI args) ─────────
TELEGRAM_BOT_TOKEN: str = ""
TELEGRAM_CHAT_ID: str = ""
TELEGRAM_STREAM: bool = True
TELEGRAM_MAX_RETRIES: int = 3
TELEGRAM_BACKOFF_BASE: float = 1.0
TELEGRAM_DRAFT_INTERVAL: float = 0.5  # min seconds between draft updates

# ── IPC ───────────────────────────────────────────────────────────
ENERGY_EMIT_INTERVAL_S: float = 0.1   # ~10 Hz energy events
MODEL_LOAD_TIMEOUT_S: float = 120.0   # includes MLX Metal shader compile on cold start
DEFAULT_ENGINE: str = "coreml"
```

### Mutating config in server.py `_do_start`
```python
# In src/server.py, inside _do_start(data: dict):
from . import config

engine = data.get("engine", config.DEFAULT_ENGINE)
device = data.get("device")
telegram_cfg = data.get("telegram")

config.INPUT_DEVICE = device  # if you add INPUT_DEVICE to config
_engine_name = engine          # local state, or also set config.DEFAULT_ENGINE

if telegram_cfg:
    config.TELEGRAM_BOT_TOKEN = telegram_cfg.get("bot_token", "")
    config.TELEGRAM_CHAT_ID = telegram_cfg.get("chat_id", "")
    config.TELEGRAM_STREAM = telegram_cfg.get("stream", True)
```

### Mutating config in realtime_demo.py `main()`
```python
# In src/realtime_demo.py, inside main():
from . import config

if args.telegram:
    from dotenv import load_dotenv
    load_dotenv()
    config.TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    config.TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("Error: --telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        sys.exit(1)
```

### Replacing print() in audio_capture.py
```python
# Before (line 75):
print(f"  Device: [{dev_idx}] {dev_name}")

# After:
log.info("Audio capture starting on device [%d] %s", dev_idx, dev_name)
```

---

## File-by-File Change Map

| File | Change | Notes |
|------|--------|-------|
| `src/config.py` | **Create** | New file. All namespaces with documented defaults |
| `src/audio_capture.py` | **Modify** | Remove `SAMPLE_RATE`, `CHANNELS`, `CHUNK_DURATION`, `CHUNK_SAMPLES`, `QUEUE_MAXSIZE` module constants; import from config. Replace `print()` on line 75 with `log.info()`. Keep `list_devices()` print calls for now (CLI utility) OR convert to log — either is acceptable. |
| `src/telegram_sender.py` | **Modify** | Remove `_MAX_RETRIES`, `_BACKOFF_BASE`, `_DRAFT_INTERVAL` module-level constants; read from config. Constructor signature unchanged. |
| `src/server.py` | **Modify** | Remove `_MODEL_LOAD_TIMEOUT = 30`; use `config.MODEL_LOAD_TIMEOUT_S`. Remove `_engine_name = "coreml"` default; use `config.DEFAULT_ENGINE`. In `_do_start`, mutate `config.TELEGRAM_BOT_TOKEN/CHAT_ID/STREAM` before constructing `TelegramSender`. |
| `src/realtime_demo.py` | **Modify** | After argparse, mutate config fields. `load_dotenv()` + write to `config.TELEGRAM_*` instead of direct `os.environ` reads into local variables. |
| `src/transcriber.py` | **Modify** | Remove `from .audio_capture import SAMPLE_RATE`; import from config. `MODEL_NAME` can stay local (it's being replaced in Phase 4 anyway). |
| `src/coreml_transcriber.py` | **Modify** | Remove `from .audio_capture import SAMPLE_RATE`; import from config. (File will be deleted in Phase 6, so minimal change.) |

---

## State of the Art

| Old Approach | Current Approach | Impact for Phase 1 |
|--------------|------------------|--------------------|
| `.env` + `python-dotenv` | Acceptable for CLI mode; none for server mode | Keep `python-dotenv` in requirements.txt (CLI convenience). Server mode already doesn't use it. |
| Scattered module constants | Move to `config.py` | Single file to edit for tuning |
| `print()` in `audio_capture.py` | `log.info()` | Removes IPC corruption risk |

---

## Open Questions

1. **Should `list_devices()` in audio_capture.py retain its `print()` calls?**
   - What we know: It's only called from `realtime_demo.py` (CLI), never from `server.py`. The success criteria don't explicitly require it.
   - What's unclear: Whether the planner wants to be strict ("no print() in src/") or pragmatic ("only the dangerous one on line 75").
   - Recommendation: Convert all `print()` in `audio_capture.py` to `log.info()`. The `realtime_demo.py` CLI sets up logging with DEBUG level anyway, so output is visible. Consistent rule is easier to enforce.

2. **Should `realtime_demo.py`'s many `print()` calls be converted?**
   - What we know: `realtime_demo.py` is a CLI tool — `print()` is intentional and correct there. It is never imported by `server.py`.
   - Recommendation: Leave `realtime_demo.py` print calls as-is. They are not IPC risk.

3. **Should `INPUT_DEVICE` and `DEFAULT_ENGINE` be mutable config fields?**
   - The `device` and `engine` values come from the `start` command at runtime. They could live in config as mutable fields, or just remain as local variables in `_do_start`.
   - Recommendation: Keep them as local variables in `_do_start` for Phase 1. Only the tunable constants (timeouts, thresholds, credentials) need to be in config. Device and engine are session choices, not application tunables.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 1 is a pure code/config reorganization. No new external tools, services, runtimes, or CLI utilities are required. Existing Python 3.11.5 venv with current dependencies is sufficient.

---

## Validation Architecture

No formal test framework was detected in this project (no pytest.ini, no tests/ directory, no test files).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ARCH-01 SC1 | CLI and SwiftUI read from same config.py | smoke | `python -c "from src import config; assert config.SAMPLE_RATE == 16000"` | ❌ Wave 0 |
| ARCH-01 SC2 | Telegram credentials not read from .env at import | manual | Start `python -m src.server`, send `start` with telegram dict, verify no .env needed | N/A |
| ARCH-01 SC3 | print() in audio_capture.py replaced with log | smoke | `python -m src.server < /dev/null 2>/dev/null \| python -c "import sys,json; [json.loads(l) for l in sys.stdin]"` — must exit 0 | ❌ Wave 0 |
| ARCH-01 SC4 | VAD/Whisper/Telegram/IPC namespaces present in config.py | smoke | `python -c "from src.config import VAD_FRAME_SIZE, WHISPER_MODEL_REPO, TELEGRAM_DRAFT_INTERVAL, ENERGY_EMIT_INTERVAL_S"` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -c "from src import config; print('config OK')"` — confirms module imports cleanly
- **Per wave merge:** Full import smoke test + IPC JSON-parse test
- **Phase gate:** All four ARCH-01 success criteria manually verified before Phase 2

### Wave 0 Gaps
- [ ] No test infrastructure exists — these are smoke commands runnable directly, no framework needed
- [ ] IPC JSON-parse smoke: `echo '{}' | python -m src.server 2>/dev/null | head -1 | python -m json.tool` — verifies first event is valid JSON

---

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis (`src/audio_capture.py`, `src/server.py`, `src/telegram_sender.py`, `src/realtime_demo.py`, `src/transcriber.py`) — all constant locations inventoried
- `.planning/research/ARCHITECTURE.md` — Config Consolidation pattern documented with recommended config.py structure
- `.planning/research/PITFALLS.md` — Pitfall 13 (AppStorage key mismatch), Pitfall 14 (audio_capture print() IPC corruption)
- `.planning/ROADMAP.md` — Phase 1 success criteria verbatim

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — confirms zero new dependencies for config consolidation

---

## Metadata

**Confidence breakdown:**
- Current constant inventory: HIGH — read directly from source files
- Migration pattern: HIGH — standard Python module mutation pattern
- File change map: HIGH — derived directly from constant locations
- Validation approach: HIGH — smoke tests are trivially constructable

**Research date:** 2026-03-27
**Valid until:** Indefinite — this is a pure code inventory; no external APIs or library versions involved
