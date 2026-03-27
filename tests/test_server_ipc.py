"""Tests for src/server.py IPC protocol — --protocol-fd and stdout fallback modes."""

import ast
import json
import os
import pathlib
import select
import subprocess
import sys
import time

# Ensure project root is on sys.path so `from src import ...` works
# when running tests directly (e.g., python tests/test_server_ipc.py)
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SERVER_PATH = pathlib.Path(_PROJECT_ROOT) / "src" / "server.py"
_TIMEOUT_S = 10


def _collect_json_lines(fd: int, timeout_s: float) -> list[dict]:
    """Read newline-delimited JSON from a file descriptor with a timeout.

    Returns a list of parsed JSON objects. Stops after the first read
    that yields no data or on timeout.
    """
    deadline = time.monotonic() + timeout_s
    buf = b""
    objects: list[dict] = []

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            break
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line:
                try:
                    objects.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if objects:
            # Got at least one event — give a tiny window for more but don't wait forever
            remaining2 = min(0.5, deadline - time.monotonic())
            if remaining2 > 0:
                r2, _, _ = select.select([fd], [], [], remaining2)
                if r2:
                    chunk2 = os.read(fd, 4096)
                    if chunk2:
                        buf += chunk2
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if line:
                                try:
                                    objects.append(json.loads(line))
                                except json.JSONDecodeError:
                                    pass
            break

    return objects


# ── Tests ────────────────────────────────────────────────────────────────────


def test_protocol_fd_writes_json_to_fd():
    """When --protocol-fd N is passed, JSON events must arrive on that fd."""
    read_fd, write_fd = os.pipe()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.server", "--protocol-fd", str(write_fd)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,  # stray stdout capture — NOT the protocol channel
        stderr=subprocess.PIPE,
        cwd=_PROJECT_ROOT,
        env=env,
        pass_fds=(write_fd,),
    )

    # Close write end in parent — child owns its copy
    os.close(write_fd)

    try:
        # Send list_devices and close stdin to let server exit cleanly
        proc.stdin.write(b'{"cmd":"list_devices"}\n')
        proc.stdin.flush()
        proc.stdin.close()

        objects = _collect_json_lines(read_fd, _TIMEOUT_S)

        assert objects, "Expected at least one JSON event on the protocol fd, got none"
        event_keys = [obj.get("event") for obj in objects]
        assert any("event" in obj for obj in objects), (
            f"No object with 'event' key in: {objects}"
        )
        _ = event_keys  # used for debugging; suppress linter warning
    finally:
        os.close(read_fd)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_no_protocol_fd_writes_to_stdout():
    """Without --protocol-fd, JSON events must arrive on stdout."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=_PROJECT_ROOT,
        env=env,
    )

    try:
        proc.stdin.write(b'{"cmd":"list_devices"}\n')
        proc.stdin.flush()
        proc.stdin.close()

        objects = _collect_json_lines(proc.stdout.fileno(), _TIMEOUT_S)

        assert objects, "Expected at least one JSON event on stdout, got none"
        assert any("event" in obj for obj in objects), (
            f"No object with 'event' key in: {objects}"
        )
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_dup2_hack_absent():
    """server.py must not contain the os.dup2 / os.dup( redirect hack."""
    text = _SERVER_PATH.read_text()
    assert "os.dup2" not in text, (
        "server.py still contains 'os.dup2' — the stdout redirect hack must be removed"
    )
    assert "os.dup(" not in text, (
        "server.py still contains 'os.dup(' — the stdout redirect hack must be removed"
    )


def test_no_bare_print():
    """server.py must have zero bare print() calls (file=sys.stderr is acceptable elsewhere)."""
    tree = ast.parse(_SERVER_PATH.read_text())
    bare_prints = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        )
    ]
    assert len(bare_prints) == 0, (
        f"server.py contains {len(bare_prints)} bare print() call(s) — "
        "use log.* or write to sys.stderr explicitly"
    )


if __name__ == "__main__":
    # Allow running directly: python tests/test_server_ipc.py
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
