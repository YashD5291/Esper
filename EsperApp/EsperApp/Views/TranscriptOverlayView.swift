import AppKit
import SwiftUI

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
        let padding: CGFloat = 28 // vertical padding top + bottom
        return CGFloat(viewModel.maxLines) * (lineHeight + spacing) - spacing + padding
    }

    var body: some View {
        HStack(spacing: 0) {
            statusStrip
            ScrollViewReader { proxy in
                ScrollView(.vertical, showsIndicators: true) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(viewModel.lines) { line in
                            lineView(line)
                        }
                    }
                    .padding(.horizontal, 18)
                    .padding(.vertical, 14)
                }
                .onChange(of: viewModel.lines.last?.id) { _, newID in
                    if let id = newID {
                        proxy.scrollTo(id, anchor: .bottom)
                    }
                }
            }
        }
        .frame(width: 560, alignment: .leading)
        .frame(maxHeight: maxHeight)
        .compositingGroup()
        .opacity(viewModel.opacity)
        .transaction { $0.disablesAnimations = true }
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
            .foregroundStyle(.white.opacity(lineOpacity(line, isLowConfidence: isLowConfidence)))
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
