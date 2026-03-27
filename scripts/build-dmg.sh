#!/usr/bin/env bash
set -euo pipefail

# ── Parse arguments ──────────────────────────────────────────────────────────
VERSION=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --version) VERSION="$2"; shift 2 ;;
        *) echo "Usage: $0 [--version X.Y.Z]"; exit 1 ;;
    esac
done

# Auto-detect version from git tag if not provided
if [[ -z "$VERSION" ]]; then
    VERSION=$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')
    if [[ -z "$VERSION" ]]; then
        echo "ERROR: No --version provided and no git tag found"
        exit 1
    fi
fi

echo "==> Building Esper v${VERSION}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/build"
STAGING="$BUILD_DIR/staging"
APP="$STAGING/Esper.app"
RESOURCES="$APP/Contents/Resources"
DIST="$PROJECT_DIR/dist"

# ── Clean ────────────────────────────────────────────────────────────────────
rm -rf "$BUILD_DIR" "$DIST"
mkdir -p "$DIST"

# ── 1. Build the Swift app ───────────────────────────────────────────────────
echo "==> Building Swift app..."
xcodebuild -project "$PROJECT_DIR/EsperApp/EsperApp.xcodeproj" \
    -scheme EsperApp \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR/derived" \
    MARKETING_VERSION="$VERSION" \
    CURRENT_PROJECT_VERSION="$(git rev-list --count HEAD)" \
    clean build 2>&1 | tail -5

# Find the built .app
BUILT_APP=$(find "$BUILD_DIR/derived" -name "EsperApp.app" -type d | head -1)
if [[ -z "$BUILT_APP" ]]; then
    echo "ERROR: Built .app not found"
    exit 1
fi

# ── 2. Stage the app ────────────────────────────────────────────────────────
echo "==> Staging app bundle..."
mkdir -p "$STAGING"
cp -R "$BUILT_APP" "$APP"

# ── 3. Embed Python runtime ─────────────────────────────────────────────────
echo "==> Embedding Python runtime..."
VENV="$PROJECT_DIR/.venv"
PYTHON_VERSION="3.11"

if [[ ! -d "$VENV" ]]; then
    echo "ERROR: .venv not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Copy Python interpreter and stdlib
PYTHON_PREFIX=$("$VENV/bin/python3" -c "import sys; print(sys.base_prefix)")
mkdir -p "$RESOURCES/python/bin" "$RESOURCES/python/lib"
cp "$VENV/bin/python3" "$RESOURCES/python/bin/python3"
cp -R "$PYTHON_PREFIX/lib/python${PYTHON_VERSION}" "$RESOURCES/python/lib/"

# Copy site-packages (installed deps)
cp -R "$VENV/lib/python${PYTHON_VERSION}/site-packages" "$RESOURCES/site-packages"

# ── 4. Embed source and models ──────────────────────────────────────────────
echo "==> Embedding source and models..."
cp -R "$PROJECT_DIR/src" "$RESOURCES/src"
mkdir -p "$RESOURCES/models"
cp -R "$PROJECT_DIR/models/whisper" "$RESOURCES/models/whisper"
cp "$PROJECT_DIR/models/silero_vad.onnx" "$RESOURCES/models/silero_vad.onnx"

# ── 5. Strip unnecessary files ──────────────────────────────────────────────
echo "==> Stripping unnecessary files..."
find "$RESOURCES" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RESOURCES" -name "*.pyc" -delete 2>/dev/null || true
find "$RESOURCES" -name "*.pyo" -delete 2>/dev/null || true
find "$RESOURCES/site-packages" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RESOURCES/site-packages" -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RESOURCES/site-packages" -name "test" -type d -exec rm -rf {} + 2>/dev/null || true
# Remove torch if it snuck in as a transitive dep
rm -rf "$RESOURCES/site-packages/torch" \
       "$RESOURCES/site-packages/torchaudio" \
       "$RESOURCES/site-packages/silero_vad" 2>/dev/null || true
# Remove pip/setuptools/wheel
rm -rf "$RESOURCES/site-packages/pip" \
       "$RESOURCES/site-packages/setuptools" \
       "$RESOURCES/site-packages/wheel" \
       "$RESOURCES/site-packages/_distutils_hack" 2>/dev/null || true

# ── 6. Create DMG ───────────────────────────────────────────────────────────
DMG_NAME="Esper-${VERSION}-arm64.dmg"
echo "==> Creating $DMG_NAME..."
hdiutil create \
    -volname "Esper" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DIST/$DMG_NAME"

# ── 7. Checksum ─────────────────────────────────────────────────────────────
shasum -a 256 "$DIST/$DMG_NAME" > "$DIST/$DMG_NAME.sha256"

# ── Done ─────────────────────────────────────────────────────────────────────
SIZE=$(du -sh "$DIST/$DMG_NAME" | cut -f1)
echo ""
echo "==> Done!"
echo "    DMG:  $DIST/$DMG_NAME ($SIZE)"
echo "    SHA:  $(cat "$DIST/$DMG_NAME.sha256")"
