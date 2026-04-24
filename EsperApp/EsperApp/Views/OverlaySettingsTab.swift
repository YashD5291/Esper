import SwiftUI

struct OverlaySettingsTab: View {
    @Bindable var settings: AppSettings
    var overlayController: OverlayController?

    @State private var style = "modern"
    @State private var textSize = "medium"
    @State private var textColor = "#FFFFFF"
    @State private var maxLines = 3
    @State private var opacity = 1.0
    @State private var showTelegramStatus = true
    @State private var autoDismiss = false
    @State private var autoDismissSeconds = 30
    @State private var flowButtonEnabled = true

    var body: some View {
        Form {
            Section("Style") {
                Picker("Overlay Style", selection: $style) {
                    Text("Minimal").tag("minimal")
                    Text("Modern").tag("modern")
                }
                .pickerStyle(.segmented)
                Text(style == "minimal"
                    ? "Just text on screen. Use Option+Space or the menu bar to control."
                    : "Toolbar with device picker, waveform, and stop button.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if style == "modern" {
                Section("Appearance") {
                    textSizeControl
                    textColorControl
                    linesControl
                    opacityControl
                }

                Section("Indicators") {
                    Toggle("Show Telegram Status", isOn: $showTelegramStatus)
                    Text("Show sent/queued indicators on each line when Telegram is enabled")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Dismiss") {
                    Toggle("Auto-dismiss after stopping", isOn: $autoDismiss)
                    if autoDismiss {
                        Picker("After", selection: $autoDismissSeconds) {
                            Text("10 seconds").tag(10)
                            Text("30 seconds").tag(30)
                            Text("60 seconds").tag(60)
                            Text("2 minutes").tag(120)
                        }
                    }
                }
            }

            Section("Flow Button") {
                Toggle("Show Flow Button", isOn: $flowButtonEnabled)
                Text("Floating button for quick start/stop. You can also use Option+Space.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section {
                Text(style == "modern"
                    ? "Right-click the overlay for quick settings. Drag to reposition."
                    : "Drag to reposition.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .onAppear {
            loadFromSettings()
            overlayController?.previewMode = true
        }
        .onDisappear { overlayController?.previewMode = false }
        .onChange(of: textSize) { _, val in settings.overlayTextSize = val }
        .onChange(of: textColor) { _, val in settings.overlayTextColor = val }
        .onChange(of: maxLines) { _, val in settings.overlayMaxLines = val }
        .onChange(of: opacity) { _, val in settings.overlayOpacity = val }
        .onChange(of: showTelegramStatus) { _, val in settings.overlayShowTelegramStatus = val }
        .onChange(of: autoDismiss) { _, val in settings.overlayAutoDismiss = val }
        .onChange(of: autoDismissSeconds) { _, val in settings.overlayAutoDismissSeconds = val }
        .onChange(of: flowButtonEnabled) { _, val in settings.flowButtonEnabled = val }
        .onChange(of: style) { _, val in settings.overlayStyle = val }
    }

    private func loadFromSettings() {
        style = settings.overlayStyle
        textSize = settings.overlayTextSize
        textColor = settings.overlayTextColor
        maxLines = settings.overlayMaxLines
        opacity = settings.overlayOpacity
        showTelegramStatus = settings.overlayShowTelegramStatus
        autoDismiss = settings.overlayAutoDismiss
        autoDismissSeconds = settings.overlayAutoDismissSeconds
        flowButtonEnabled = settings.flowButtonEnabled
    }

    // MARK: - Appearance Controls

    private var textSizeControl: some View {
        HStack {
            Text("Text Size")
            Spacer()
            Picker("", selection: $textSize) {
                Text("S").tag("small")
                Text("M").tag("medium")
                Text("L").tag("large")
            }
            .pickerStyle(.segmented)
            .frame(width: 120)
        }
    }

    private var parsedColor: Color {
        Color.fromHex(textColor)
    }

    private var textColorControl: some View {
        HStack {
            Text("Text Color")
            Spacer()
            let presets: [(String, Color)] = [
                ("#FFFFFF", .white),
                ("#4CAF50", .green),
                ("#42A5F5", .blue),
                ("#FFA726", .orange),
                ("#EF5350", .red),
            ]
            ForEach(presets, id: \.0) { hex, color in
                Circle()
                    .fill(color)
                    .frame(width: 22, height: 22)
                    .overlay(
                        Circle()
                            .stroke(
                                textColor == hex ? Color.accentColor : Color.clear,
                                lineWidth: 2
                            )
                    )
                    .onTapGesture { textColor = hex }
            }

            Divider().frame(height: 18)

            ColorPicker("", selection: Binding(
                get: { parsedColor },
                set: { newColor in
                    if let hex = newColor.toHex() {
                        textColor = hex
                    }
                }
            ), supportsOpacity: false)
            .labelsHidden()
            .frame(width: 22)
        }
    }

    private var linesControl: some View {
        HStack {
            Text("Lines")
            Spacer()
            Text("\(maxLines)")
                .monospacedDigit()
                .frame(minWidth: 20, alignment: .trailing)
            Stepper("", value: $maxLines, in: 1...9)
                .labelsHidden()
        }
    }

    private var opacityControl: some View {
        HStack {
            Text("Opacity")
            Spacer()
            Text("\(Int(opacity * 100))%")
                .foregroundStyle(.secondary)
                .monospacedDigit()
                .frame(width: 40, alignment: .trailing)
            Slider(value: $opacity, in: 0.3...1.0, step: 0.05)
                .frame(width: 140)
        }
    }
}

// MARK: - Color Hex Conversion

extension Color {
    static func fromHex(_ hex: String) -> Color {
        guard hex.hasPrefix("#"),
              hex.count == 7,
              let val = UInt64(hex.dropFirst(), radix: 16)
        else { return .white }
        let r = Double((val >> 16) & 0xFF) / 255
        let g = Double((val >> 8) & 0xFF) / 255
        let b = Double(val & 0xFF) / 255
        return Color(red: r, green: g, blue: b)
    }

    func toHex() -> String? {
        guard let nsColor = NSColor(self).usingColorSpace(.sRGB) else { return nil }
        let r = Int(nsColor.redComponent * 255)
        let g = Int(nsColor.greenComponent * 255)
        let b = Int(nsColor.blueComponent * 255)
        return String(format: "#%02X%02X%02X", r, g, b)
    }
}
