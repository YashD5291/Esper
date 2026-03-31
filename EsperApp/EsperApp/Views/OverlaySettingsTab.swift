import SwiftUI

struct OverlaySettingsTab: View {
    @Bindable var settings: AppSettings
    var overlayController: OverlayController?

    var body: some View {
        Form {
            Section {
                Toggle("Show Overlay", isOn: $settings.overlayEnabled)
            }

            if settings.overlayEnabled {
                Section("Position") {
                    positionPicker
                }

                Section("Appearance") {
                    textSizeControl
                    textColorControl
                    linesControl
                    opacityControl
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { overlayController?.previewMode = true }
        .onDisappear { overlayController?.previewMode = false }
    }

    // MARK: - Position Picker (Mini Screen)

    private var positionPicker: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(nsColor: .controlBackgroundColor).opacity(0.5))
                .aspectRatio(16.0 / 10.0, contentMode: .fit)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                )
                .overlay(positionDots)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
    }

    private var positionDots: some View {
        GeometryReader { geo in
            let margin: CGFloat = 16
            let dotSize: CGFloat = 12
            let positions: [(OverlayPosition, CGFloat, CGFloat)] = [
                (.topLeft, margin, margin),
                (.topCenter, geo.size.width / 2 - dotSize / 2, margin),
                (.topRight, geo.size.width - margin - dotSize, margin),
                (.bottomLeft, margin, geo.size.height - margin - dotSize),
                (.bottomCenter, geo.size.width / 2 - dotSize / 2, geo.size.height - margin - dotSize),
                (.bottomRight, geo.size.width - margin - dotSize, geo.size.height - margin - dotSize),
            ]

            ForEach(positions, id: \.0) { pos, x, y in
                let isSelected = settings.parsedOverlayPosition == pos
                Circle()
                    .fill(isSelected ? Color.accentColor : Color.secondary.opacity(0.3))
                    .frame(width: dotSize, height: dotSize)
                    .shadow(color: isSelected ? Color.accentColor.opacity(0.6) : .clear, radius: 4)
                    .position(x: x + dotSize / 2, y: y + dotSize / 2)
                    .onTapGesture {
                        settings.overlayPosition = pos.rawValue
                    }
            }
        }
    }

    // MARK: - Appearance Controls

    private var textSizeControl: some View {
        HStack {
            Text("Text Size")
            Spacer()
            Picker("", selection: $settings.overlayTextSize) {
                Text("S").tag("small")
                Text("M").tag("medium")
                Text("L").tag("large")
            }
            .pickerStyle(.segmented)
            .frame(width: 120)
        }
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
                                settings.overlayTextColor == hex ? Color.accentColor : Color.clear,
                                lineWidth: 2
                            )
                    )
                    .onTapGesture { settings.overlayTextColor = hex }
            }

            Divider().frame(height: 18)

            ColorPicker("", selection: Binding(
                get: { settings.parsedOverlayColor },
                set: { newColor in
                    if let hex = newColor.toHex() {
                        settings.overlayTextColor = hex
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
            Stepper(
                value: $settings.overlayMaxLines,
                in: 1...9
            ) {
                Text("\(settings.overlayMaxLines)")
                    .monospacedDigit()
                    .frame(minWidth: 20, alignment: .center)
            }
        }
    }

    private var opacityControl: some View {
        HStack {
            Text("Opacity")
            Spacer()
            Text("\(Int(settings.overlayOpacity * 100))%")
                .foregroundStyle(.secondary)
                .monospacedDigit()
                .frame(width: 40, alignment: .trailing)
            Slider(value: $settings.overlayOpacity, in: 0.3...1.0, step: 0.05)
                .frame(width: 140)
        }
    }
}

// MARK: - Color Hex Conversion

extension Color {
    func toHex() -> String? {
        guard let nsColor = NSColor(self).usingColorSpace(.sRGB) else { return nil }
        let r = Int(nsColor.redComponent * 255)
        let g = Int(nsColor.greenComponent * 255)
        let b = Int(nsColor.blueComponent * 255)
        return String(format: "#%02X%02X%02X", r, g, b)
    }
}
