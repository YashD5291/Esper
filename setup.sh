#!/usr/bin/env bash
#
# Esper setup script — installs Python dependencies, downloads models,
# and optionally builds the SwiftUI app.
#
# Usage:
#   ./setup.sh          # Full setup (Python + models + app)
#   ./setup.sh --cli    # Python + models only (skip Xcode build)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BOLD}==> ${NC}$1"; }
ok()    { echo -e "${GREEN}  ✓ ${NC}$1"; }
warn()  { echo -e "${YELLOW}  ! ${NC}$1"; }
fail()  { echo -e "${RED}  ✗ ${NC}$1"; exit 1; }

CLI_ONLY=false
if [[ "${1:-}" == "--cli" ]]; then
    CLI_ONLY=true
fi

# ── 1. Check macOS ─────────────────────────────────────────────────
info "Checking macOS version..."
MACOS_VERSION=$(sw_vers -productVersion)
MAJOR=$(echo "$MACOS_VERSION" | cut -d. -f1)
if [[ "$MAJOR" -lt 14 ]]; then
    fail "macOS 14 (Sonoma) or later required. You have $MACOS_VERSION."
fi
ok "macOS $MACOS_VERSION"

# ── 2. Check Python ────────────────────────────────────────────────
info "Checking Python..."
if command -v python3 &>/dev/null; then
    PY=$(command -v python3)
else
    fail "Python 3 not found. Install Python 3.11 via pyenv or python.org."
fi

PY_VERSION=$($PY --version 2>&1 | awk '{print $2}')
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f1,2)
if [[ "$PY_MINOR" != "3.11" && "$PY_MINOR" != "3.12" && "$PY_MINOR" != "3.13" ]]; then
    warn "Python $PY_VERSION detected. Python 3.11–3.13 recommended."
fi
ok "Python $PY_VERSION ($PY)"

# ── 3. Check ffmpeg ────────────────────────────────────────────────
info "Checking ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg not found. Installing via Homebrew..."
    if command -v brew &>/dev/null; then
        brew install ffmpeg
        ok "ffmpeg installed"
    else
        fail "ffmpeg is required. Install Homebrew (https://brew.sh) then run: brew install ffmpeg"
    fi
else
    ok "ffmpeg found"
fi

# ── 4. Create venv and install dependencies ────────────────────────
info "Setting up Python virtual environment..."
if [[ ! -d .venv ]]; then
    $PY -m venv .venv
    ok "Created .venv"
else
    ok ".venv already exists"
fi

source .venv/bin/activate
ok "Activated .venv ($(python --version))"

info "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
ok "Dependencies installed"

# ── 5. Download CoreML models ──────────────────────────────────────
info "Checking CoreML models..."
if [[ -d models/coreml/MelEncoder.mlmodelc ]]; then
    ok "CoreML models already downloaded"
else
    info "Downloading CoreML models (~200MB)..."
    python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    'FluidInference/parakeet-tdt-0.6b-v3-coreml',
    local_dir='models/coreml'
)
"
    ok "CoreML models downloaded to models/coreml/"
fi

# ── 6. Verify Python setup ────────────────────────────────────────
info "Verifying Python setup..."
python -c "
import sounddevice, numpy, coremltools, httpx
print('  All imports OK')
" || fail "Python import check failed. Check error above."
ok "Python environment ready"

# ── 7. Build SwiftUI app (optional) ───────────────────────────────
if [[ "$CLI_ONLY" == true ]]; then
    warn "Skipping Xcode build (--cli flag)"
else
    info "Checking Xcode..."
    if ! command -v xcodebuild &>/dev/null; then
        warn "Xcode command line tools not found. Skipping app build."
        warn "Install Xcode 15+ from the App Store to build the menu bar app."
    else
        info "Building EsperApp..."
        xcodebuild \
            -project EsperApp/EsperApp.xcodeproj \
            -scheme EsperApp \
            -configuration Release \
            build \
            2>&1 | tail -5

        # Find the built app
        BUILD_DIR=$(xcodebuild \
            -project EsperApp/EsperApp.xcodeproj \
            -scheme EsperApp \
            -configuration Release \
            -showBuildSettings 2>/dev/null \
            | grep -m1 'BUILT_PRODUCTS_DIR' \
            | awk '{print $3}')
        APP_PATH="$BUILD_DIR/EsperApp.app"

        if [[ -d "$APP_PATH" ]]; then
            ok "Built $APP_PATH"
            echo ""
            read -rp "$(echo -e "${BOLD}Copy EsperApp.app to /Applications? [y/N]${NC} ")" INSTALL
            if [[ "$INSTALL" =~ ^[Yy]$ ]]; then
                cp -R "$APP_PATH" /Applications/
                ok "Installed to /Applications/EsperApp.app"
            fi
        else
            warn "Build succeeded but could not locate .app bundle"
        fi
    fi
fi

# ── Done ───────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Setup complete!${NC}"
echo ""
echo "  CLI usage:"
echo "    source .venv/bin/activate"
echo "    python -m src.realtime_demo"
echo ""
if [[ "$CLI_ONLY" != true ]]; then
    echo "  App usage:"
    echo "    Open EsperApp from /Applications or Xcode"
    echo ""
fi
echo "  For Telegram integration, create a .env file:"
echo "    TELEGRAM_BOT_TOKEN=your-token"
echo "    TELEGRAM_CHAT_ID=your-chat-id"
