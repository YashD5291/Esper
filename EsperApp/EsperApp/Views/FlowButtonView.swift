import SwiftUI

// MARK: - Flow Button View Model

@Observable
@MainActor
final class FlowButtonViewModel {
    var engineStatus: EngineStatus = .idle
    var energyLevel: Double = 0.0
    var errorMessage: String?
    var overlayDismissed = false
}

// MARK: - Flow Button View

struct FlowButtonView: View {
    let viewModel: FlowButtonViewModel
    var onToggle: (() -> Void)?
    var onStop: (() -> Void)?
    var onReopen: (() -> Void)?

    var body: some View {
        HStack(spacing: 8) {
            switch viewModel.engineStatus {
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
        .onTapGesture {
            if viewModel.engineStatus != .listening {
                onToggle?()
            }
        }
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
