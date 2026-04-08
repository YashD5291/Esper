# Overlay Reopen via Flow Button — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add split-zone tap behavior to the flow button so users can reopen a dismissed overlay during listening.

**Architecture:** FlowButtonView's listening state splits into two tap zones (left: reopen overlay, right: stop). A chevron indicator appears when the overlay is dismissed. OverlayController feeds the dismissed state to the view model and wires the reopen callback.

**Tech Stack:** SwiftUI, NSPanel (existing FlowButton)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `EsperApp/EsperApp/Views/FlowButtonView.swift` | Modify | Add `overlayDismissed` to VM, `onReopen` callback, split listening into two zones, chevron indicator |
| `EsperApp/EsperApp/EsperApp.swift` | Modify | Feed `dismissed` to flow VM, wire `onReopen` to `reopenOverlay()` |

---

### Task 1: Split Flow Button Listening State into Two Zones

**Files:**
- Modify: `EsperApp/EsperApp/Views/FlowButtonView.swift`

- [ ] **Step 1: Add `overlayDismissed` to FlowButtonViewModel**

In `FlowButtonView.swift`, add the property after `errorMessage`:

```swift
@Observable
@MainActor
final class FlowButtonViewModel {
    var engineStatus: EngineStatus = .idle
    var energyLevel: Double = 0.0
    var errorMessage: String?
    var overlayDismissed = false
}
```

- [ ] **Step 2: Add `onReopen` callback to FlowButtonView**

Add after `onStop`:

```swift
struct FlowButtonView: View {
    let viewModel: FlowButtonViewModel
    var onToggle: (() -> Void)?
    var onStop: (() -> Void)?
    var onReopen: (() -> Void)?
```

- [ ] **Step 3: Replace the listening case with split zones**

Replace the entire `case .listening:` block (lines 23-38) with:

```swift
            case .listening:
                HStack(spacing: 0) {
                    // Left zone: waveform + chevron + label → reopens overlay
                    HStack(spacing: 8) {
                        waveformBars
                        if viewModel.overlayDismissed {
                            Image(systemName: "chevron.up")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundStyle(Color.blue.opacity(0.6))
                        }
                        Text("Listening")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.green)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        if viewModel.overlayDismissed {
                            onReopen?()
                        }
                    }

                    // Right zone: stop button
                    Button(action: { onStop?() }) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(.red)
                            .frame(width: 16, height: 16)
                            .overlay(
                                RoundedRectangle(cornerRadius: 1)
                                    .fill(.white)
                                    .frame(width: 8, height: 8)
                            )
                            .padding(.leading, 8)
                    }
                    .buttonStyle(.plain)
                }
```

- [ ] **Step 4: Remove the top-level onTapGesture for listening state**

The top-level `.onTapGesture { onToggle?() }` on line 78 still fires for ALL states. It needs to only apply to non-listening states. Replace:

```swift
        .contentShape(Rectangle())
        .onTapGesture { onToggle?() }
```

with:

```swift
        .contentShape(Rectangle())
        .onTapGesture {
            if viewModel.engineStatus != .listening {
                onToggle?()
            }
        }
```

- [ ] **Step 5: Build and verify**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

Expected: `BUILD SUCCEEDED`

- [ ] **Step 6: Commit**

```bash
git add EsperApp/EsperApp/Views/FlowButtonView.swift
git commit -m "feat: split flow button into two tap zones with chevron indicator"
```

---

### Task 2: Wire OverlayController to Flow Button Reopen

**Files:**
- Modify: `EsperApp/EsperApp/EsperApp.swift`

- [ ] **Step 1: Feed `dismissed` state to flow view model**

In `updateFlowButton()` (line 224), add after `flowViewModel.errorMessage = engine.errorMessage` (line 229):

```swift
            flowViewModel.overlayDismissed = dismissed && engine.status == .listening
```

This only shows the chevron during active listening — not in idle, processing, or error states.

- [ ] **Step 2: Wire `onReopen` callback in `ensureFlowButton()`**

In `ensureFlowButton()`, add the `onReopen` parameter to the `FlowButtonView` initializer. Replace lines 248-260:

```swift
        let host = NSHostingView(rootView: FlowButtonView(
            viewModel: flowViewModel,
            onToggle: {
                if engine.status == .listening {
                    engine.stopListening()
                } else if engine.status == .idle {
                    engine.startListening()
                }
            },
            onStop: {
                engine.stopListening()
            },
            onReopen: { [weak self] in
                self?.reopenOverlay()
            }
        ))
```

Note: `reopenOverlay()` already exists at line 326 — it sets `dismissed = false`. The next 200ms poll cycle will detect `shouldShow = true` and show the overlay.

- [ ] **Step 3: Build and verify**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

Expected: `BUILD SUCCEEDED`

- [ ] **Step 4: Run tests**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp test -destination 'platform=macOS' 2>&1 | grep -E '(passed|failed|BUILD)' | tail -5`

Expected: All tests pass, `BUILD SUCCEEDED`

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/EsperApp.swift
git commit -m "feat: wire overlay reopen to flow button left zone tap"
```
