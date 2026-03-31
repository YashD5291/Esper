import SwiftUI

struct OverlaySettingsTab: View {
    @Bindable var settings: AppSettings
    var overlayController: OverlayController?

    // Local state mirrors @AppStorage (which is @ObservationIgnored)
    @State private var enabled = false
    @State private var placementMode = "draggable"
    @State private var position = "bottomCenter"
    @State private var textSize = "medium"
    @State private var textColor = "#FFFFFF"
    @State private var maxLines = 3
    @State private var opacity = 1.0

    var body: some View {
        Form {
            Section {
                Toggle("Show Overlay", isOn: $enabled)
            }

            if enabled {
                Section("Placement") {
                    Picker("Mode", selection: $placementMode) {
                        Text("Fixed").tag("fixed")
                        Text("Draggable").tag("draggable")
                    }
                    .pickerStyle(.segmented)

                    if placementMode == "fixed" {
                        positionPicker
                    } else {
                        Text("Drag the overlay to any position on screen")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
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
        .onAppear {
            loadFromSettings()
            overlayController?.previewMode = true
        }
        .onDisappear { overlayController?.previewMode = false }
        .onChange(of: enabled) { _, val in settings.overlayEnabled = val }
        .onChange(of: placementMode) { _, val in settings.overlayPlacementMode = val }
        .onChange(of: position) { _, val in settings.overlayPosition = val }
        .onChange(of: textSize) { _, val in settings.overlayTextSize = val }
        .onChange(of: textColor) { _, val in settings.overlayTextColor = val }
        .onChange(of: maxLines) { _, val in settings.overlayMaxLines = val }
        .onChange(of: opacity) { _, val in settings.overlayOpacity = val }
    }

    private func loadFromSettings() {
        enabled = settings.overlayEnabled
        placementMode = settings.overlayPlacementMode
        position = settings.overlayPosition
        textSize = settings.overlayTextSize
        textColor = settings.overlayTextColor
        maxLines = settings.overlayMaxLines
        opacity = settings.overlayOpacity
    }

    // MARK: - Position Picker (Mini Screen)

    private var selectedPosition: OverlayPosition {
        OverlayPosition(rawValue: position) ?? .bottomCenter
    }

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
                let isSelected = selectedPosition == pos
                Circle()
                    .fill(isSelected ? Color.accentColor : Color.secondary.opacity(0.3))
                    .frame(width: dotSize, height: dotSize)
                    .shadow(color: isSelected ? Color.accentColor.opacity(0.6) : .clear, radius: 4)
                    .position(x: x + dotSize / 2, y: y + dotSize / 2)
                    .onTapGesture {
                        position = pos.rawValue
                    }
            }
        }
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
        guard textColor.hasPrefix("#"),
              textColor.count == 7,
              let hex = UInt64(textColor.dropFirst(), radix: 16)
        else { return .white }
        let r = Double((hex >> 16) & 0xFF) / 255
        let g = Double((hex >> 8) & 0xFF) / 255
        let b = Double(hex & 0xFF) / 255
        return Color(red: r, green: g, blue: b)
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
    func toHex() -> String? {
        guard let nsColor = NSColor(self).usingColorSpace(.sRGB) else { return nil }
        let r = Int(nsColor.redComponent * 255)
        let g = Int(nsColor.greenComponent * 255)
        let b = Int(nsColor.blueComponent * 255)
        return String(format: "#%02X%02X%02X", r, g, b)
    }
}
