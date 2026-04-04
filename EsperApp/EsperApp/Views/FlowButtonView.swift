import SwiftUI

// MARK: - Flow Button View Model

@Observable
@MainActor
final class FlowButtonViewModel {
    var engineStatus: EngineStatus = .idle
    var energyLevel: Double = 0.0
    var errorMessage: String?
}

// MARK: - Flow Button View

struct FlowButtonView: View {
    let viewModel: FlowButtonViewModel
    var onToggle: (() -> Void)?
    var onStop: (() -> Void)?

    var body: some View {
        HStack(spacing: 8) {
            switch viewModel.engineStatus {
            case .listening:
                waveformBars
                Text("Listening")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.green)
                Button(action: { onStop?() }) {
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

            case .transcribing:
                Circle()
                    .fill(.orange)
                    .frame(width: 8, height: 8)
                Text("Processing")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.white.opacity(0.7))

            case .idle:
                if let error = viewModel.errorMessage {
                    Circle()
                        .fill(.red)
                        .frame(width: 8, height: 8)
                    Text(String(error.prefix(30)))
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white.opacity(0.7))
                        .lineLimit(1)
                } else {
                    Circle()
                        .fill(Color(white: 0.55))
                        .frame(width: 8, height: 8)
                    Text("Esper")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white.opacity(0.5))
                }

            default:
                Circle()
                    .fill(.orange)
                    .frame(width: 8, height: 8)
                Text(viewModel.engineStatus.displayName)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.white.opacity(0.7))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .onTapGesture { onToggle?() }
    }

    // MARK: - Waveform Bars

    private var waveformBars: some View {
        HStack(spacing: 2) {
            ForEach(0..<5, id: \.self) { i in
                WaveBar(energy: viewModel.energyLevel, index: i)
            }
        }
        .frame(height: 20)
    }
}

// MARK: - Waveform Bar

private struct WaveBar: View {
    let energy: Double
    let index: Int

    private var barHeight: CGFloat {
        let base = 4.0
        let maxExtra = 16.0
        let phase = Double(index) * 0.2
        let wave = sin(Date.now.timeIntervalSinceReferenceDate * 8 + phase)
        let modulated = energy * (0.5 + 0.5 * wave)
        return base + maxExtra * min(modulated * 3, 1.0)
    }

    var body: some View {
        RoundedRectangle(cornerRadius: 1.5)
            .fill(.white)
            .frame(width: 3, height: barHeight)
            .animation(.linear(duration: 0.1), value: energy)
    }
}
