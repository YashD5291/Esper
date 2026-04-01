#!/bin/bash
set -euo pipefail

# Usage: ./scripts/release.sh 3.2.0 "Fixed foo, added bar"
VERSION="${1:?Usage: release.sh <version> <release-notes>}"
NOTES="${2:?Usage: release.sh <version> <release-notes>}"
TAG="v${VERSION}"

# Fail early if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "Error: Tag $TAG already exists. Use a different version."
    exit 1
fi
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DMG_PATH="$PROJECT_DIR/dist/Esper-${VERSION}-arm64.dmg"
APPCAST="$PROJECT_DIR/docs/appcast.xml"
SIGN_TOOL=$(find ~/Library/Developer/Xcode/DerivedData/EsperApp-*/SourcePackages/artifacts -name "sign_update" 2>/dev/null | head -1)

if [ -z "$SIGN_TOOL" ]; then
    echo "Error: sign_update not found. Build in Xcode first to resolve Sparkle package."
    exit 1
fi

echo "=== Building Full DMG (PyInstaller + Swift) ==="
"$PROJECT_DIR/scripts/build-dmg.sh" --version "$VERSION"

if [ ! -f "$DMG_PATH" ]; then
    echo "Error: DMG not found at $DMG_PATH"
    exit 1
fi

echo "=== Signing DMG with EdDSA ==="
SIGN_OUTPUT=$("$SIGN_TOOL" "$DMG_PATH")
echo "$SIGN_OUTPUT"

ED_SIG=$(echo "$SIGN_OUTPUT" | grep -o 'sparkle:edSignature="[^"]*"' | cut -d'"' -f2)
LENGTH=$(echo "$SIGN_OUTPUT" | grep -o 'length="[^"]*"' | cut -d'"' -f2)

if [ -z "$ED_SIG" ] || [ -z "$LENGTH" ]; then
    echo "Error: Failed to parse signature output"
    exit 1
fi

# Build number = git commit count (must match CURRENT_PROJECT_VERSION in build-dmg.sh)
NEW_BUILD=$(git rev-list --count HEAD)
PUB_DATE=$(date -u "+%a, %d %b %Y %H:%M:%S +0000")
DMG_NAME="Esper-${VERSION}-arm64.dmg"

# Format release notes as HTML list items (with entity escaping)
escape_html() { sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g'; }
NOTES_HTML=$(echo "$NOTES" | escape_html | tr ',' '\n' | sed 's/^ *//' | sed 's/.*/          <li>&<\/li>/')

echo "=== Updating appcast.xml ==="
cp "$APPCAST" "$APPCAST.bak"
cat > "$APPCAST" << EOF
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Esper Updates</title>
    <link>https://yashd5291.github.io/Esper/appcast.xml</link>
    <description>Esper app updates</description>
    <language>en</language>
    <item>
      <title>Version ${VERSION}</title>
      <sparkle:version>${NEW_BUILD}</sparkle:version>
      <sparkle:shortVersionString>${VERSION}</sparkle:shortVersionString>
      <description><![CDATA[
        <ul>
${NOTES_HTML}
        </ul>
      ]]></description>
      <pubDate>${PUB_DATE}</pubDate>
      <enclosure
        url="https://github.com/YashD5291/Esper/releases/download/${TAG}/${DMG_NAME}"
        sparkle:edSignature="${ED_SIG}"
        length="${LENGTH}"
        type="application/octet-stream"
      />
    </item>
  </channel>
</rss>
EOF

echo "=== Committing & Pushing ==="
git add "$APPCAST"
git commit -m "release: ${TAG}"
git tag -a "$TAG" -m "${TAG}: ${NOTES}"
git push origin main
git push origin "$TAG"

echo "=== Creating GitHub Release ==="
if ! gh release create "$TAG" "$DMG_PATH" \
    --title "${TAG}" \
    --notes "$(echo "$NOTES" | tr ',' '\n' | sed 's/^ */- /')"; then
    echo "Error: GitHub release creation failed. Tag and commit are pushed — create release manually:"
    echo "  gh release create ${TAG} ${DMG_PATH} --title ${TAG}"
    exit 1
fi

echo ""
echo "=== Done! ==="
echo "Release: https://github.com/YashD5291/Esper/releases/tag/${TAG}"
echo "Appcast will be live at: https://yashd5291.github.io/Esper/appcast.xml"
