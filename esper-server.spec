# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for esper-server (onedir bundle)."""

import os, sys

block_cipher = None

# ── paths ──────────────────────────────────────────────────────────────
PROJECT = os.path.abspath('.')
VENV_SITE = os.path.join(PROJECT, '.venv', 'lib', 'python3.11', 'site-packages')

from PyInstaller.utils.hooks import collect_all

# Collect ALL files for packages with C extensions that PyInstaller misses
scipy_datas, scipy_binaries, scipy_hiddenimports = collect_all('scipy')
mlx_datas, mlx_binaries, mlx_hiddenimports = collect_all('mlx')
mlxw_datas, mlxw_binaries, mlxw_hiddenimports = collect_all('mlx_whisper')

a = Analysis(
    ['esper_server_entry.py'],
    pathex=[PROJECT],
    binaries=[
        (os.path.join(VENV_SITE, 'mlx', 'lib', 'mlx.metallib'), 'mlx/lib'),
    ] + scipy_binaries + mlx_binaries + mlxw_binaries,
    datas=[
        ('models/silero_vad.onnx', 'models'),
        ('models/whisper', 'models/whisper'),
    ] + scipy_datas + mlx_datas + mlxw_datas,
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
        # MLX internals
        'mlx._reprlib_fix',
        # MLX / Whisper
        'mlx_whisper',
        'mlx',
        'mlx.core',
        'huggingface_hub',
    ] + scipy_hiddenimports + mlx_hiddenimports + mlxw_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchaudio', 'torchvision', 'torchgen', 'functorch',
        'tensorflow', 'tensorboard',
        'pytest', 'IPython', 'jupyter',
        'matplotlib', 'PIL', 'tkinter',
        'hf_xet',
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
    strip=True,
    upx=False,
    console=True,
    target_arch='arm64',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name='esper-server',
)
