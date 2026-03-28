"""Subprocess worker loop for Whisper inference (Phase 4).

Runs in a spawn-context child process. Loads the Whisper model once,
then loops reading numpy audio arrays from audio_q and posting result
dicts to result_q. The parent process (WhisperTranscriber) applies
hallucination filtering; this module only runs inference.

IMPORTANT: word_timestamps and clip_timestamps must NOT be passed to
mlx_whisper.transcribe() — they cause crashes on some audio inputs.
"""

from __future__ import annotations

import logging
import pathlib
import sys

# Add project root to sys.path so 'from . import config' works in spawn context.
# Spawn does not inherit the parent's runtime sys.path modifications.
_FROZEN = getattr(sys, '_MEIPASS', None)
_PROJECT_ROOT = _FROZEN if _FROZEN else str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _whisper_worker(audio_q, result_q) -> None:
    """Top-level subprocess worker. Loads model once, loops until sentinel.

    Args:
        audio_q: SimpleQueue from parent. Receives numpy float32 arrays
                 (complete utterances) or None (shutdown sentinel).
        result_q: SimpleQueue to parent. Sends result dicts:
                  {"ok": True, "result": <raw mlx_whisper dict>}
                  {"ok": False, "error": <str>}
                  {"ok": True, "ready": True}  (startup sentinel)
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s worker: %(message)s",
    )
    log = logging.getLogger("esper.whisper_worker")

    # Import here so model loading happens in the child process
    try:
        import mlx_whisper
        from src import config
    except ImportError as exc:
        result_q.put({"ok": False, "error": f"ImportError in worker: {exc}"})
        return

    log.info("Whisper worker ready. Model repo: %s", config.WHISPER_MODEL_REPO)

    # Emit ready sentinel so parent knows model is reachable
    result_q.put({"ok": True, "ready": True})

    while True:
        audio = audio_q.get()

        if audio is None:
            log.debug("Received shutdown sentinel, exiting worker loop.")
            break

        try:
            raw = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=config.WHISPER_MODEL_REPO,
                language=config.WHISPER_LANGUAGE,
                word_timestamps=False,
                condition_on_previous_text=False,
                temperature=0.0,
                no_speech_threshold=None,         # filtering done in parent (D-07)
                compression_ratio_threshold=None,  # filtering done in parent (D-07)
            )
            result_q.put({"ok": True, "result": raw})
        except Exception as exc:
            log.error("Inference error: %s", exc, exc_info=True)
            result_q.put({"ok": False, "error": str(exc)})
