"""
Esper Phase 1: STT Proof of Concept with Parakeet TDT v3

Records audio from the microphone, transcribes it using NVIDIA Parakeet TDT v3
(via parakeet-mlx on Apple Silicon), and prints the results.

Usage:
    # Record and transcribe a single 10-second clip
    python tests/test_stt.py

    # Custom duration
    python tests/test_stt.py --duration 5

    # Benchmark mode: record 10 sentences back-to-back
    python tests/test_stt.py --benchmark

    # Transcribe an existing WAV file
    python tests/test_stt.py --file path/to/audio.wav

    # Use a specific audio device (see --list-devices)
    python tests/test_stt.py --device 0

    # List available audio devices
    python tests/test_stt.py --list-devices
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
CHANNELS = 1
MODEL_NAME = "mlx-community/parakeet-tdt-0.6b-v3"
OUTPUT_DIR = Path(__file__).parent.parent / "recordings"


def list_devices():
    """Print available audio input devices."""
    print("\nAvailable audio input devices:")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            default = " (DEFAULT)" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}{default}")


def find_real_mic() -> int | None:
    """Find the built-in microphone device index, skipping loopback devices."""
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            name = dev["name"].lower()
            if "microphone" in name and "loopback" not in name:
                return i
    return None


def record_audio(duration: float, device: int | None = None) -> np.ndarray:
    """Record audio from the microphone."""
    dev_name = sd.query_devices(device)["name"] if device is not None else "default"
    print(f"\n--- Recording for {duration}s via [{device or 'default'}] {dev_name} ---")
    print("Speak now!", flush=True)

    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        device=device,
    )
    sd.wait()

    print("Recording complete.")
    return audio.flatten()


def save_wav(audio: np.ndarray, path: Path) -> Path:
    """Save audio as a 16kHz mono WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, SAMPLE_RATE)
    print(f"Saved: {path}")
    return path


def load_model():
    """Load the Parakeet TDT v3 model."""
    from parakeet_mlx import from_pretrained

    print(f"\nLoading model: {MODEL_NAME}")
    t0 = time.time()
    model = from_pretrained(MODEL_NAME)
    load_time = time.time() - t0
    print(f"Model loaded in {load_time:.1f}s")
    return model


def transcribe(model, audio_path: Path) -> dict:
    """Transcribe a WAV file and return results with timing info."""
    print(f"\nTranscribing: {audio_path.name}")
    t0 = time.time()
    result = model.transcribe(str(audio_path))
    latency = time.time() - t0

    return {
        "text": result.text,
        "latency": latency,
        "sentences": [
            {
                "text": s.text.strip(),
                "start": s.start,
                "end": s.end,
                "confidence": s.confidence,
            }
            for s in result.sentences
        ],
    }


def print_result(result: dict):
    """Pretty-print transcription results."""
    print(f"\n{'='*60}")
    print(f"TRANSCRIPTION: {result['text']}")
    print(f"LATENCY:       {result['latency']:.2f}s")
    print(f"{'='*60}")

    if result["sentences"]:
        print("\nSegments:")
        for i, seg in enumerate(result["sentences"], 1):
            conf = f"{seg['confidence']:.0%}" if seg["confidence"] else "N/A"
            print(
                f"  [{seg['start']:.2f}s - {seg['end']:.2f}s] "
                f"(conf: {conf}) {seg['text']}"
            )


def single_test(model, duration: float, device: int | None = None):
    """Record a single clip and transcribe it."""
    audio = record_audio(duration, device=device)
    wav_path = save_wav(audio, OUTPUT_DIR / "test_clip.wav")
    result = transcribe(model, wav_path)
    print_result(result)


def file_test(model, file_path: str):
    """Transcribe an existing audio file."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)
    result = transcribe(model, path)
    print_result(result)


def benchmark(model, duration: float = 5.0, num_sentences: int = 10, device: int | None = None):
    """Record and transcribe multiple sentences for accuracy benchmarking."""
    test_phrases = [
        "The quick brown fox jumps over the lazy dog",
        "Please schedule a meeting for three thirty PM tomorrow",
        "The API endpoint returns a JSON response with status code two hundred",
        "My phone number is nine eight seven six five four three two one zero",
        "Kumar and Priya are working on the deployment pipeline",
        "The neural network achieved ninety five percent accuracy on the test set",
        "Can you send me the pull request link on Slack",
        "The server is running on port eight zero eight zero",
        "Mumbai is approximately one thousand four hundred kilometers from Delhi",
        "We need to refactor the authentication middleware before the release",
    ]

    print("\n" + "=" * 60)
    print("BENCHMARK MODE")
    print(f"Recording {num_sentences} sentences, {duration}s each")
    print("=" * 60)

    results = []
    for i in range(num_sentences):
        print(f"\n--- Sentence {i+1}/{num_sentences} ---")
        print(f'EXPECTED: "{test_phrases[i]}"')
        input("Press Enter when ready to speak...")

        audio = record_audio(duration, device=device)
        wav_path = save_wav(audio, OUTPUT_DIR / f"benchmark_{i+1:02d}.wav")
        result = transcribe(model, wav_path)

        print(f'GOT:      "{result["text"]}"')
        print(f"LATENCY:  {result['latency']:.2f}s")

        results.append(
            {
                "expected": test_phrases[i],
                "got": result["text"],
                "latency": result["latency"],
            }
        )

    # Print summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)

    total_latency = sum(r["latency"] for r in results)
    avg_latency = total_latency / len(results)

    for i, r in enumerate(results, 1):
        match = "~" if r["expected"].lower().strip() == r["got"].lower().strip() else "X"
        print(f"  [{match}] {i}. Expected: {r['expected']}")
        print(f"       Got:      {r['got']}")
        print(f"       Latency:  {r['latency']:.2f}s")

    print(f"\nAverage latency: {avg_latency:.2f}s")
    print("Review the above manually for Word Error Rate.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Esper Phase 1: STT Test")
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Recording duration in seconds (default: 10)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run benchmark mode with 10 test sentences",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Transcribe an existing audio file instead of recording",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="Audio input device index (see --list-devices)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        sys.exit(0)

    # Auto-detect real mic if no device specified and default is loopback
    device = args.device
    if device is None:
        default_name = sd.query_devices(sd.default.device[0])["name"].lower()
        if "loopback" in default_name:
            real_mic = find_real_mic()
            if real_mic is not None:
                print(f"Default input is loopback — using MacBook mic (device {real_mic}) instead.")
                device = real_mic

    model = load_model()

    if args.file:
        file_test(model, args.file)
    elif args.benchmark:
        benchmark(model, duration=args.duration, device=device)
    else:
        single_test(model, args.duration, device=device)


if __name__ == "__main__":
    main()
