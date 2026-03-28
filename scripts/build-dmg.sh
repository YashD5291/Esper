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
ENTITLEMENTS="$PROJECT_DIR/EsperApp/EsperApp/EsperApp.entitlements"

# ── Clean ────────────────────────────────────────────────────────────────────
rm -rf "$BUILD_DIR" "$DIST"
mkdir -p "$DIST"

# ── 1. Freeze Python server with PyInstaller ────────────────────────────────
echo "==> Freezing Python server..."
if [[ ! -d "$PROJECT_DIR/.venv" ]]; then
    echo "ERROR: .venv not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

"$PROJECT_DIR/.venv/bin/pyinstaller" "$PROJECT_DIR/esper-server.spec" \
    --noconfirm \
    --distpath "$BUILD_DIR/frozen" \
    --workpath "$BUILD_DIR/pyinstaller-work"

FROZEN_DIR="$BUILD_DIR/frozen/esper-server"
if [[ ! -f "$FROZEN_DIR/esper-server" ]]; then
    echo "ERROR: Frozen binary not found at $FROZEN_DIR/esper-server"
    exit 1
fi

echo "    Frozen server: $(du -sh "$FROZEN_DIR" | cut -f1)"

# ── 2. Build the Swift app ───────────────────────────────────────────────────
echo "==> Building Swift app..."
xcodebuild -project "$PROJECT_DIR/EsperApp/EsperApp.xcodeproj" \
    -scheme EsperApp \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR/derived" \
    MARKETING_VERSION="$VERSION" \
    CURRENT_PROJECT_VERSION="$(git rev-list --count HEAD)" \
    clean build

BUILT_APP=$(find "$BUILD_DIR/derived" -name "EsperApp.app" -type d | head -1)
if [[ -z "$BUILT_APP" ]]; then
    echo "ERROR: Built .app not found"
    exit 1
fi

# ── 3. Stage the app bundle ─────────────────────────────────────────────────
echo "==> Staging app bundle..."
mkdir -p "$STAGING"
cp -R "$BUILT_APP" "$APP"

# ── 4. Embed frozen server ──────────────────────────────────────────────────
echo "==> Embedding frozen server..."
cp -R "$FROZEN_DIR" "$RESOURCES/esper-server"

# ── 5. Sign the app bundle ──────────────────────────────────────────────────
echo "==> Signing app bundle..."

# Sign all Mach-O files inside the frozen server directory
find "$RESOURCES/esper-server" -type f | while read -r f; do
    file "$f" | grep -q "Mach-O" && codesign --force --sign - "$f"
done

# Sign the app bundle with entitlements (must be last)
codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP"

# ── 6. Verify bundle ────────────────────────────────────────────────────────
echo "==> Verifying bundle..."
# Check frozen binary exists and is signed
codesign --verify "$RESOURCES/esper-server/esper-server" || { echo "ERROR: Frozen binary signature invalid"; exit 1; }
codesign --verify "$APP" || { echo "ERROR: App signature invalid"; exit 1; }
# Check entitlements
codesign -d --entitlements - "$APP" 2>&1 | grep -q "audio-input" || { echo "ERROR: Audio entitlement missing"; exit 1; }
# Check no torch snuck in
if find "$RESOURCES" -name "torch" -type d 2>/dev/null | grep -q .; then
    echo "WARNING: torch found in bundle — check PyInstaller excludes"
fi
echo "    All checks passed."

# ── 7. Create DMG ───────────────────────────────────────────────────────────
DMG_NAME="Esper-${VERSION}-arm64.dmg"
echo "==> Creating $DMG_NAME..."
hdiutil create \
    -volname "Esper" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DIST/$DMG_NAME"

# ── 8. Checksum ─────────────────────────────────────────────────────────────
shasum -a 256 "$DIST/$DMG_NAME" > "$DIST/$DMG_NAME.sha256"

# ── Done ─────────────────────────────────────────────────────────────────────
SIZE=$(du -sh "$DIST/$DMG_NAME" | cut -f1)
echo ""
echo "==> Done!"
echo "    DMG:  $DIST/$DMG_NAME ($SIZE)"
echo "    SHA:  $(cat "$DIST/$DMG_NAME.sha256")"
