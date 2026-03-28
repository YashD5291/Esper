"""Single source of truth for all Esper tunables.

Every component imports from here. Mutation happens only at startup
(in server._do_start or realtime_demo.main) before any component is
constructed.
"""

import pathlib
import sys

_FROZEN = getattr(sys, '_MEIPASS', None)
_PROJECT_ROOT = pathlib.Path(_FROZEN) if _FROZEN else pathlib.Path(__file__).resolve().parent.parent

# ── Audio ──────────────────────────────────────────────────────────────────────
SAMPLE_RATE: int = 16000
CHANNELS: int = 1
CHUNK_DURATION: float = 0.032          # 512 / 16000 = 32ms (hard Silero VAD requirement)
CHUNK_SAMPLES: int = int(SAMPLE_RATE * CHUNK_DURATION)  # 512 samples at 16kHz = 32ms
QUEUE_MAXSIZE: int = 300               # ~9.6s of buffered audio at 512 samples/frame

# ── VAD (Phase 3) ──────────────────────────────────────────────────────────────
VAD_FRAME_SIZE: int = 512              # samples at 16kHz = 32ms (hard Silero requirement)
VAD_SPEECH_THRESHOLD: float = 0.3     # aggressive — catch soft/quick speech
VAD_SILENCE_THRESHOLD_MS: int = 300   # seal utterances fast (300ms silence)
VAD_MIN_SPEECH_DURATION_MS: int = 100 # catch even single-word utterances (~100ms)
VAD_MIN_ENERGY: float = 0.003         # very low floor — don't reject quiet speech
VAD_PRE_BUFFER_MS: int = 300          # speech onset context prepended to utterance
VAD_POST_BUFFER_MS: int = 200         # silence context appended after speech ends
VAD_MODEL_PATH: str = str(_PROJECT_ROOT / "models" / "silero_vad.onnx")

# ── Whisper (Phase 4) ──────────────────────────────────────────────────────────
WHISPER_MODEL_REPO: str = str(_PROJECT_ROOT / "models" / "whisper")
WHISPER_LANGUAGE: str = "en"
WHISPER_MAX_GENERATIONS_BEFORE_RESTART: int = 50
WHISPER_SUBPROCESS_TIMEOUT_S: float = 15.0
WHISPER_NO_SPEECH_THRESHOLD: float = 0.8   # only filter obvious non-speech
WHISPER_COMPRESSION_RATIO_THRESHOLD: float = 3.0  # only filter extreme repetition

# ── Telegram (set at runtime via start command / CLI args) ─────────────────────
TELEGRAM_BOT_TOKEN: str = ""           # set at runtime via start command / CLI args
TELEGRAM_CHAT_ID: str = ""
TELEGRAM_MAX_RETRIES: int = 3
TELEGRAM_BACKOFF_BASE: float = 1.0

# ── IPC ────────────────────────────────────────────────────────────────────────
ENERGY_EMIT_INTERVAL_S: float = 0.1   # ~10 Hz energy events
MODEL_LOAD_TIMEOUT_S: float = 120.0   # includes MLX Metal shader compile on cold start
