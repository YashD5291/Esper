"""Continuous microphone capture with queue-based chunk delivery."""

import logging
import math
import queue
import threading

import numpy as np
import sounddevice as sd

from . import config

log = logging.getLogger(__name__)


def list_devices():
    """Print available audio input devices."""
    log.info("Available audio input devices:")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            default = " (DEFAULT)" if i == sd.default.device[0] else ""
            log.info("  [%d] %s%s", i, dev['name'], default)


def find_real_mic() -> int | None:
    """Find the built-in microphone device index, skipping loopback devices."""
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            name = dev["name"].lower()
            if "microphone" in name and "loopback" not in name:
                return i
    return None


def auto_select_device(requested: int | None = None) -> int | None:
    """Pick the best input device.

    If *requested* is given, use it directly. Otherwise, check if the system
    default is a loopback device and fall back to the real mic.
    """
    if requested is not None:
        return requested
    default_idx = sd.default.device[0]
    default_name = sd.query_devices(default_idx)["name"].lower()
    if "loopback" in default_name:
        real = find_real_mic()
        if real is not None:
            return real
    return None  # let sounddevice use its own default


class AudioCapture:
    """Captures microphone audio in a background thread via sounddevice.

    Audio is delivered as 0.1 s float32 chunks through a queue.
    """

    def __init__(self, device: int | None = None):
        self.device = auto_select_device(device)
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=config.QUEUE_MAXSIZE)
        self._stream: sd.InputStream | None = None
        self._energy: float = 0.0
        self._drop_count: int = 0
        self._lock = threading.Lock()

    # -- public API --

    def start(self):
        dev_idx = self.device if self.device is not None else sd.default.device[0]
        dev_info = sd.query_devices(dev_idx)
        dev_name = dev_info["name"]
        log.info("Audio capture starting on device [%d] %s", dev_idx, dev_name)

        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="float32",
            blocksize=config.CHUNK_SAMPLES,
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        # sentinel so consumer knows we're done
        self._queue.put(None)

    def get_chunk(self, timeout: float = 1.0) -> np.ndarray | None:
        """Return the next audio chunk, or None if capture has stopped."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return np.zeros(0, dtype=np.float32)  # empty, not sentinel

    @property
    def energy(self) -> float:
        """Most recent RMS energy (0.0–1.0 scale)."""
        with self._lock:
            return self._energy

    # -- internal --

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            status_str = str(status)
            if "error" in status_str.lower() or "overflow" in status_str.lower():
                log.error("Audio device error: %s", status)
            else:
                log.warning("Audio stream status: %s", status)
        chunk = indata[:, 0].copy()  # (frames,) float32
        rms = math.sqrt(float(np.mean(chunk ** 2)))
        with self._lock:
            self._energy = rms
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            self._drop_count += 1
            if self._drop_count % 100 == 1:  # Log every 100th drop (first, 101st, 201st...)
                log.warning("Audio queue full — dropped %d frames (consumer too slow)", self._drop_count)
