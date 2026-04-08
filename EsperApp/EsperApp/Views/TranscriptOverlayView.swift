import AppKit
import SwiftUI

// MARK: - Panel Mode

enum PanelMode: Equatable {
    case pill
    case overlay
}

// MARK: - Line State

enum LineState: Equatable {
    case draft
    case finalized
    case queued
    case sent
}

// MARK: - View Model (mutated by OverlayController, observed by view)

@Observable
@MainActor
final class OverlayViewModel {
    var lines: [OverlayLine] = []
    var engineStatus: EngineStatus = .idle
    var fontSize: CGFloat = 15
    var textColor: Color = .white
    var opacity: Double = 1.0
    var maxLines: Int = 3
    var showTelegramStatus: Bool = true
    var energyLevel: Double = 0.0
    var devices: [AudioDevice] = []
    var selectedDevice: Int? = nil
    var errorMessage: String? = nil
    var onSelectDevice: ((Int) -> Void)?
    var onDismiss: (() -> Void)?
    var onOpenSettings: (() -> Void)?

    // Panel morph state
    var mode: PanelMode = .pill
    var overlayDismissed = false

    // Additional callbacks
    var onToggle: (() -> Void)?
    var onStop: (() -> Void)?
    var onCollapse: (() -> Void)?
}

struct OverlayLine: Identifiable, Equatable {
    let id: String
    let text: String
    let state: LineState
    let confidence: Double // 0.0-1.0 (inverted from no_speech_prob)
}

// MARK: - View

struct TranscriptOverlayView: View {
    let viewModel: OverlayViewModel

    /// Visible height: maxLines * (fontSize * lineHeight + spacing) + padding
    private var maxHeight: CGFloat {
        let lineHeight = viewModel.fontSize * 1.4
        let spacing: CGFloat = 6
        let padding: CGFloat = 28
        let errorHeight: CGFloat = viewModel.errorMessage != nil ? 34 : 0
        return topBarHeight + CGFloat(viewModel.maxLines) * (lineHeight + spacing) - spacing + padding + errorHeight
    }

    var body: some View {
        HStack(spacing: 0) {
            if viewModel.onStop == nil {
                statusStrip
            }
            VStack(spacing: 0) {
                topBar
                ScrollViewReader { proxy in
                    ScrollView(.vertical, showsIndicators: true) {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(viewModel.lines) { line in
                                lineView(line)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 14)
                        .transaction { $0.disablesAnimations = true }
                    }
                    .onChange(of: viewModel.lines.last?.id) { _, newID in
                        if let id = newID {
                            proxy.scrollTo(id, anchor: .bottom)
                        }
                    }
                }
                if let error = viewModel.errorMessage {
                    errorBar(error)
                }
            }
        }
        .frame(width: 560, alignment: .leading)
        .frame(maxHeight: maxHeight)
        .compositingGroup()
        .opacity(viewModel.opacity)
    }

    // MARK: - Top Bar

    private let topBarHeight: CGFloat = 32

    private var topBar: some View {
        HStack(spacing: 0) {
            if viewModel.onStop != nil {
                // Left: device picker + settings
                if !viewModel.devices.isEmpty {
                    Picker("", selection: Binding(
                        get: { viewModel.selectedDevice ?? -1 },
                        set: { if $0 != -1 { viewModel.onSelectDevice?($0) } }
                    )) {
                        ForEach(viewModel.devices) { device in
                            Text(device.name).tag(device.index)
                        }
                    }
                    .labelsHidden()
                    .controlSize(.mini)
                    .font(.system(size: 10))
                    .frame(maxWidth: 140)
                }

                Button(action: { viewModel.onOpenSettings?() }) {
                    Image(systemName: "gearshape")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.white.opacity(0.35))
                }
                .buttonStyle(.plain)
                .padding(.leading, 6)

                Spacer()

                // Right: waveform + stop + close
                HStack(spacing: 8) {
                    overlayWaveformBars
                    Rectangle()
                        .fill(.white.opacity(0.08))
                        .frame(width: 1, height: 16)
                    Button(action: { viewModel.onStop?() }) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(.red)
                            .frame(width: 16, height: 16)
                            .overlay(
                                RoundedRectangle(cornerRadius: 1)
                                    .fill(.white)
                                    .frame(width: 8, height: 8)
                            )
                    }
                    .buttonStyle(.plain)
                    Button(action: { viewModel.onCollapse?() }) {
                        Image(systemName: "xmark")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.35))
                    }
                    .buttonStyle(.plain)
                }
            } else {
                // Legacy mode — audio meter + device picker + gear + dismiss
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(.white.opacity(0.08))
                        .frame(width: 80, height: 3)
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(.green)
                        .frame(width: 80 * min(viewModel.energyLevel * 3, 1.0), height: 3)
                }

                if !viewModel.devices.isEmpty {
                    Picker("", selection: Binding(
                        get: { viewModel.selectedDevice ?? -1 },
                        set: { if $0 != -1 { viewModel.onSelectDevice?($0) } }
                    )) {
                        ForEach(viewModel.devices) { device in
                            Text(device.name).tag(device.index)
                        }
                    }
                    .labelsHidden()
                    .controlSize(.mini)
                    .font(.system(size: 10))
                    .frame(maxWidth: 140)
                    .padding(.leading, 6)
                }

                Spacer()

                Button(action: { viewModel.onOpenSettings?() }) {
                    Image(systemName: "gearshape")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.white.opacity(0.35))
                }
                .buttonStyle(.plain)
                .padding(.trailing, 4)

                Button(action: { viewModel.onDismiss?() }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.35))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .frame(height: topBarHeight)
        .background(.white.opacity(0.02))
        .overlay(alignment: .bottom) {
            Rectangle().fill(.white.opacity(0.06)).frame(height: 1)
        }
    }

    private var overlayWaveformBars: some View {
        WaveformLine(energy: viewModel.energyLevel, width: 50, height: 20, lineWidth: 1.5)
    }

    // MARK: - Error Bar

    private func errorBar(_ message: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 11))
            Text(message)
                .font(.system(size: 12))
                .lineLimit(2)
        }
        .foregroundStyle(Color(red: 1, green: 0.27, blue: 0.23))
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(red: 1, green: 0.27, blue: 0.23).opacity(0.15))
        .overlay(alignment: .top) {
            Rectangle().fill(Color(red: 1, green: 0.27, blue: 0.23).opacity(0.2)).frame(height: 1)
        }
    }

    // MARK: - Status Strip

    private var statusStrip: some View {
        Rectangle()
            .fill(statusStripColor)
            .frame(width: 3)
            .opacity(0.65)
    }

    private var statusStripColor: Color {
        switch viewModel.engineStatus {
        case .listening: .green
        case .transcribing: .orange
        case .idle: .gray
        default: .red
        }
    }

    // MARK: - Line Rendering

    @ViewBuilder
    private func lineView(_ line: OverlayLine) -> some View {
        let isLowConfidence = line.confidence < 0.3 && line.state != .draft
        HStack(spacing: 0) {
            if viewModel.showTelegramStatus {
                lineBorder(line, isLowConfidence: isLowConfidence)
                    .frame(width: 3)
                    .padding(.trailing, 12)
            }

            Group {
                if line.state == .draft {
                    HStack(spacing: 0) {
                        Text(line.text)
                        caretView
                    }
                } else {
                    HStack(spacing: 4) {
                        Text(line.text)
                            .italic(isLowConfidence)
                        if viewModel.showTelegramStatus {
                            lineIndicator(line, isLowConfidence: isLowConfidence)
                        }
                    }
                }
            }
            .font(.system(size: viewModel.fontSize, weight: .medium))
            .tracking(0.3)
            .lineSpacing(viewModel.fontSize * 0.4)
            .foregroundStyle(viewModel.textColor.opacity(lineOpacity(line, isLowConfidence: isLowConfidence)))
        }
        .id(line.id)
    }

    private func lineOpacity(_ line: OverlayLine, isLowConfidence: Bool) -> Double {
        if isLowConfidence { return 0.4 }
        switch line.state {
        case .draft: return 0.55
        case .finalized: return 0.75
        case .queued: return 0.75
        case .sent: return 0.95
        }
    }

    @ViewBuilder
    private func lineBorder(_ line: OverlayLine, isLowConfidence: Bool) -> some View {
        if isLowConfidence {
            Rectangle()
                .fill(.orange.opacity(0.35))
                .mask(
                    VStack(spacing: 2) {
                        ForEach(0..<8, id: \.self) { _ in
                            Rectangle().frame(height: 2)
                        }
                    }
                )
        } else {
            Rectangle().fill(lineBorderColor(line))
        }
    }

    private func lineBorderColor(_ line: OverlayLine) -> Color {
        switch line.state {
        case .draft: .white.opacity(0.15)
        case .finalized: .clear
        case .queued: .orange
        case .sent: .green
        }
    }

    @ViewBuilder
    private func lineIndicator(_ line: OverlayLine, isLowConfidence: Bool) -> some View {
        if isLowConfidence {
            Text("?")
                .font(.system(size: 10))
                .foregroundStyle(.orange.opacity(0.5))
        } else {
            switch line.state {
            case .sent:
                Text("✓")
                    .font(.system(size: 10))
                    .foregroundStyle(.green)
            case .queued:
                Text("●")
                    .font(.system(size: 10))
                    .foregroundStyle(.orange)
            default:
                EmptyView()
            }
        }
    }

    // MARK: - Caret

    private var caretView: some View {
        Rectangle()
            .fill(.white.opacity(0.5))
            .frame(width: 2, height: viewModel.fontSize)
    }
}
