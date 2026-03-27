"""Single source of truth for all Esper tunables.

Every component imports from here. Mutation happens only at startup
(in server._do_start or realtime_demo.main) before any component is
constructed.
"""

# ── Audio ──────────────────────────────────────────────────────────────────────
SAMPLE_RATE: int = 16000
CHANNELS: int = 1
CHUNK_DURATION: float = 0.032          # 512 / 16000 = 32ms (hard Silero VAD requirement)
CHUNK_SAMPLES: int = int(SAMPLE_RATE * CHUNK_DURATION)  # 512 samples at 16kHz = 32ms
QUEUE_MAXSIZE: int = 300               # ~9.6s of buffered audio at 512 samples/frame

# ── VAD (Phase 3) ──────────────────────────────────────────────────────────────
VAD_FRAME_SIZE: int = 512              # samples at 16kHz = 32ms (hard Silero requirement)
VAD_SPEECH_THRESHOLD: float = 0.5     # probability above which frame is speech
VAD_SILENCE_THRESHOLD_MS: int = 500   # ms of silence to seal an utterance
VAD_MIN_SPEECH_DURATION_MS: int = 500 # discard utterances shorter than this
VAD_MIN_ENERGY: float = 0.01          # RMS floor; discard very quiet frames

# ── Whisper (Phase 4) ──────────────────────────────────────────────────────────
WHISPER_MODEL_REPO: str = "mlx-community/whisper-large-v3-turbo"
WHISPER_LANGUAGE: str = "en"
WHISPER_MAX_GENERATIONS_BEFORE_RESTART: int = 50
WHISPER_SUBPROCESS_TIMEOUT_S: float = 15.0
WHISPER_NO_SPEECH_THRESHOLD: float = 0.6
WHISPER_COMPRESSION_RATIO_THRESHOLD: float = 2.4

# ── Telegram (set at runtime via start command / CLI args) ─────────────────────
TELEGRAM_BOT_TOKEN: str = ""           # set at runtime via start command / CLI args
TELEGRAM_CHAT_ID: str = ""
TELEGRAM_STREAM: bool = True
TELEGRAM_MAX_RETRIES: int = 3
TELEGRAM_BACKOFF_BASE: float = 1.0
TELEGRAM_DRAFT_INTERVAL: float = 0.5  # min seconds between draft updates

# ── IPC ────────────────────────────────────────────────────────────────────────
ENERGY_EMIT_INTERVAL_S: float = 0.1   # ~10 Hz energy events
MODEL_LOAD_TIMEOUT_S: float = 120.0   # includes MLX Metal shader compile on cold start
DEFAULT_ENGINE: str = "coreml"
