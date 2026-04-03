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
    var isHovering: Bool = false
    var showTelegramStatus: Bool = true
}

struct OverlayLine: Identifiable, Equatable {
    let id: String
    let text: String
    let state: LineState
    let confidence: Double // 0.0-1.0 (inverted from no_speech_prob)
}

// MARK: - View (placeholder - rebuilt in Task 5)

struct TranscriptOverlayView: View {
    let viewModel: OverlayViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(viewModel.lines) { line in
                Text(line.text)
                    .font(.system(size: viewModel.fontSize, weight: .medium))
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
        .frame(width: 560, alignment: .leading)
        .transaction { $0.disablesAnimations = true }
    }
}
