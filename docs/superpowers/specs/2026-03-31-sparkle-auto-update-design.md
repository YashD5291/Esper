# Sparkle Auto-Update Integration

## Goal

Add automatic update delivery to the Esper macOS app so users receive new versions without manually downloading DMGs. Uses the Sparkle 2 framework with EdDSA signing, GitHub Pages-hosted appcast, and full auto-install (download, verify, replace, relaunch).

## Architecture

### Overview

Sparkle 2 is added as a Swift Package Manager dependency. The app initializes `SPUStandardUpdaterController` at launch, which handles the entire update lifecycle. An appcast XML file hosted on GitHub Pages advertises available versions. Each DMG is signed with an EdDSA key; the public key is embedded in the app for verification.

### Components

| Component | Responsibility |
|-----------|---------------|
| `SPUStandardUpdaterController` | Sparkle's built-in update controller. Manages check schedule, UI dialogs, download, verification, install, relaunch. |
| `SUFeedURL` (Info.plist) | Points to `https://yashd5291.github.io/Esper/appcast.xml` |
| `SUPublicEDKey` (Info.plist) | EdDSA public key for verifying update signatures |
| `SUScheduledCheckInterval` (Info.plist) | 86400 (24-hour automatic check interval) |
| `docs/appcast.xml` | GitHub Pages source. Contains version entries with DMG download URL, EdDSA signature, file size, and release notes. |
| EdDSA key pair | Private key stored locally on dev machine (`~/.sparkle_eddsa_key` or project-local). Used by `generate_appcast` to sign DMGs. |

### Data Flow

```
App launch
  -> SPUStandardUpdaterController checks last check timestamp
  -> If >24h (or manual trigger): GET appcast.xml from GitHub Pages
  -> Parse XML, compare sparkle:version against CFBundleVersion
  -> If newer version available:
     -> Show Sparkle update dialog (release notes, version, Install/Skip/Remind)
     -> User clicks Install
     -> Download DMG from GitHub Releases URL in appcast
     -> Verify EdDSA signature against embedded SUPublicEDKey
     -> Extract .app from DMG, replace running app
     -> Relaunch
```

## App Changes

### 1. Add Sparkle SPM Dependency

Add `https://github.com/sparkle-project/Sparkle` (version 2.x, up to next major) to the Xcode project via Swift Package Manager.

### 2. Info.plist Keys (via Build Settings)

Since the project uses `GENERATE_INFOPLIST_FILE = YES`, keys are added through build settings in the Xcode project, not a physical Info.plist file:

- `SUFeedURL` = `https://yashd5291.github.io/Esper/appcast.xml`
- `SUPublicEDKey` = (generated EdDSA public key, base64-encoded)
- `SUScheduledCheckInterval` = `86400`

### 3. EsperApp.swift

Initialize `SPUStandardUpdaterController` as a `@State` property:

```swift
@State private var updaterController = SPUStandardUpdaterController(
    startingUpdater: true,
    updaterDelegate: nil,
    userDriverDelegate: nil
)
```

`startingUpdater: true` makes Sparkle begin its automatic check schedule immediately. Pass the updater controller to SettingsView and MenuBarView.

### 4. MenuBarView.swift

Add a "Check for Updates..." button that calls `updaterController.checkForUpdates(nil)`. Place it above the Quit button with a divider.

### 5. SettingsView.swift — Updates Tab

Add a 5th tab "Updates" (icon: `arrow.triangle.2.circlepath`) with:

- **Toggle**: "Automatically check for updates" — bound to `updaterController.updater.automaticallyChecksForUpdates`
- **Label**: "Current version: v{CFBundleShortVersionString}" — read from `Bundle.main`
- **Button**: "Check for Updates" — calls `updaterController.checkForUpdates(nil)`

### 6. Appcast (docs/appcast.xml)

Hosted via GitHub Pages from the `docs/` directory (or a `gh-pages` branch). Example structure:

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Esper Updates</title>
    <item>
      <title>Version 3.0.1</title>
      <sparkle:version>3.0.1</sparkle:version>
      <sparkle:shortVersionString>3.0.1</sparkle:shortVersionString>
      <description><![CDATA[
        <ul>
          <li>Fixed overlay blink during live transcription</li>
          <li>Rendering hardening for overlay panel</li>
        </ul>
      ]]></description>
      <pubDate>Mon, 31 Mar 2026 00:00:00 +0000</pubDate>
      <enclosure
        url="https://github.com/YashD5291/Esper/releases/download/v3.0.1/Esper.dmg"
        sparkle:edSignature="BASE64_EDDSA_SIGNATURE"
        length="DMG_FILE_SIZE_BYTES"
        type="application/octet-stream"
      />
    </item>
  </channel>
</rss>
```

### 7. GitHub Pages Setup

Enable GitHub Pages on the repository serving from `docs/` directory on `main` branch. The appcast URL becomes `https://yashd5291.github.io/Esper/appcast.xml`.

## Release Workflow

When publishing a new version:

1. Build DMG via `scripts/build-dmg.sh`
2. Sign the DMG with Sparkle's `generate_appcast` tool (or `sign_update` tool):
   ```bash
   # Sign the DMG and get the EdDSA signature + file size
   ./bin/sign_update Esper.dmg
   ```
3. Add a new `<item>` entry to `docs/appcast.xml` with the version, signature, file size, download URL, and release notes
4. Commit and push to main (GitHub Pages auto-deploys the appcast)
5. Create GitHub release with the DMG attached (the download URL in the appcast points to this release asset)

## EdDSA Key Management

- Generate key pair once: `generate_keys` (Sparkle CLI tool, installed via SPM build)
- Private key: stored in `~/.config/sparkle/eddsa_key` (never committed)
- Public key: embedded in app via `SUPublicEDKey` Info.plist key
- If the private key is lost, existing users cannot verify new updates — they must manually download

## Security Model

- No macOS Keychain involvement — EdDSA verification is pure in-memory crypto
- No Apple Developer certificate required — EdDSA is independent of Apple code signing
- Update integrity verified by matching the DMG's EdDSA signature against the embedded public key
- Appcast served over HTTPS (GitHub Pages)
- DMG downloaded over HTTPS (GitHub Releases)

## Testing

- Unit test: verify `SUFeedURL` and `SUPublicEDKey` are set in the bundle's Info dictionary
- Manual smoke test: publish a test version with higher version number, verify update dialog appears, install works, app relaunches
- Test automatic check by setting `SUScheduledCheckInterval` to a short value (e.g., 60 seconds) during development

## Files Changed/Created

| File | Action |
|------|--------|
| `EsperApp.xcodeproj` | Add Sparkle SPM dependency, add Info.plist keys via build settings |
| `EsperApp/EsperApp.swift` | Initialize SPUStandardUpdaterController, pass to views |
| `EsperApp/Views/MenuBarView.swift` | Add "Check for Updates..." menu item |
| `EsperApp/Views/SettingsView.swift` | Add "Updates" tab |
| `EsperApp/Views/UpdateSettingsTab.swift` | New file: Updates settings tab view |
| `docs/appcast.xml` | New file: Sparkle appcast for GitHub Pages |
| `EsperApp/EsperApp.entitlements` | No changes needed (sandbox already disabled) |
