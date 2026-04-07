import SwiftUI

// MARK: - Esper Panel View

struct EsperPanelView: View {
    let viewModel: OverlayViewModel

    var body: some View {
        ZStack {
            if viewModel.mode == .pill {
                pillContent
                    .transition(.opacity)
            } else {
                overlayContent
                    .transition(.opacity.combined(with: .scale(scale: 0.97, anchor: .bottom)))
            }
        }
        .animation(.easeInOut(duration: 0.15), value: viewModel.mode)
        .clipped()
    }

    // MARK: - Pill Content

    private var pillContent: some View {
        HStack(spacing: 8) {
            switch viewModel.engineStatus {
            case .listening, .transcribing, .downloadingModel, .compilingShaders, .loadingModel:
                HStack(spacing: 0) {
                    // Left zone: waveform + chevron + label
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
                            viewModel.onToggle?()
                        }
                    }

                    // Separator
                    Rectangle()
                        .fill(.white.opacity(0.08))
                        .frame(width: 1, height: 16)
                        .padding(.horizontal, 6)

                    // Right zone: stop button
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
                }

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
                EmptyView()
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .onTapGesture {
            if viewModel.engineStatus == .idle {
                viewModel.onToggle?()
            }
        }
    }

    // MARK: - Overlay Content

    private var overlayContent: some View {
        TranscriptOverlayView(viewModel: viewModel)
    }

    // MARK: - Waveform Bars

    private var waveformBars: some View {
        HStack(spacing: 2) {
            ForEach(0..<5, id: \.self) { i in
                PillWaveBar(energy: viewModel.energyLevel, index: i)
            }
        }
        .frame(height: 20)
    }
}

// MARK: - Pill Wave Bar

private struct PillWaveBar: View {
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
