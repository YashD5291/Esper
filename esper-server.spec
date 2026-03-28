# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for esper-server (onedir bundle)."""

import os, sys

block_cipher = None

# ── paths ──────────────────────────────────────────────────────────────
PROJECT = os.path.abspath('.')

a = Analysis(
    ['esper_server_entry.py'],
    pathex=[PROJECT],
    binaries=[],
    datas=[
        ('models/silero_vad.onnx', 'models'),
        ('models/whisper', 'models/whisper'),
    ],
    hiddenimports=[
        # project modules
        'src',
        'src.config',
        'src.audio_capture',
        'src.vad',
        'src.vad_model',
        'src.transcriber',
        'src.whisper_worker',
        'src.telegram_sender',
        # numpy 2.x internals (PyInstaller hook misses these)
        'numpy._core._exceptions',
        'numpy._core._methods',
        'numpy._core._dtype_ctypes',
        'numpy._core._internal',
        # native / C-extension packages
        'onnxruntime',
        'onnxruntime.capi',
        'onnxruntime.capi._pybind_state',
        '_sounddevice_data',
        # MLX / Whisper
        'mlx_whisper',
        'mlx',
        'mlx.core',
        'huggingface_hub',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchaudio', 'torchvision', 'torchgen', 'functorch',
        'tensorflow', 'tensorboard',
        'pytest', 'IPython', 'jupyter',
        'matplotlib', 'PIL', 'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='esper-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch='arm64',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='esper-server',
)
