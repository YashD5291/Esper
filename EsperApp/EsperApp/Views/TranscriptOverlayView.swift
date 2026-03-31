import SwiftUI

// MARK: - View Model (mutated by OverlayController, observed by view)

@Observable
@MainActor
final class OverlayViewModel {
    var lines: [OverlayLine] = []
    var fontSize: CGFloat = 20
    var textColor: Color = .white
    var opacity: Double = 1.0
}

struct OverlayLine: Identifiable, Equatable {
    let id: String
    let text: String
    let dimmed: Bool
}

// MARK: - View (never replaced, observes view model)

struct TranscriptOverlayView: View {
    let viewModel: OverlayViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(viewModel.lines) { line in
                Text(line.text)
                    .font(.system(size: viewModel.fontSize, weight: .medium, design: .rounded))
                    .foregroundStyle(viewModel.textColor)
                    .shadow(color: .black.opacity(0.7), radius: 2, x: 1, y: 1)
                    .opacity(line.dimmed ? 0.5 : 1.0)
                    .transition(.asymmetric(
                        insertion: .move(edge: .bottom).combined(with: .opacity),
                        removal: .opacity
                    ))
                    .id(line.id)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: viewModel.lines.map(\.id))
        .opacity(viewModel.opacity)
        .padding(.horizontal, 28)
        .padding(.vertical, 16)
        .frame(width: 660, alignment: .leading)
    }
}
