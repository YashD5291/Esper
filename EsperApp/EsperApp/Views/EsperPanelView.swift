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
                if viewModel.style == "minimal" {
                    HStack(spacing: 8) {
                        waveformBars
                        if viewModel.overlayDismissed {
                            Image(systemName: "chevron.up")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundStyle(.primary.opacity(0.5))
                        }
                        Text("Listening")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.primary.opacity(0.85))
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        if viewModel.overlayDismissed {
                            viewModel.onToggle?()
                        }
                    }
                } else {
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
                }

            case .idle:
                if let error = viewModel.errorMessage {
                    Circle()
                        .fill(.red)
                        .frame(width: 8, height: 8)
                    Text(String(error.prefix(30)))
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(viewModel.style == "minimal" ? Color.primary.opacity(0.85) : Color.white.opacity(0.7))
                        .lineLimit(1)
                } else {
                    Circle()
                        .fill(viewModel.style == "minimal" ? Color.primary.opacity(0.4) : Color(white: 0.55))
                        .frame(width: 8, height: 8)
                    Text("Esper")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(viewModel.style == "minimal" ? Color.primary.opacity(0.65) : Color.white.opacity(0.5))
                }
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

    // MARK: - Waveform

    private var waveformBars: some View {
        WaveformLine(energy: viewModel.energyLevel)
    }
}

// MARK: - Waveform Line

struct WaveformLine: View {
    let energy: Double
    var width: CGFloat = 40
    var height: CGFloat = 20
    var lineWidth: CGFloat = 2
    var color: Color = .white

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { timeline in
            Canvas { context, size in
                let t: CGFloat = CGFloat(timeline.date.timeIntervalSinceReferenceDate)
                let midY: CGFloat = size.height / 2
                let e: CGFloat = CGFloat(energy)

                // Baseline idle ripple so the line always feels alive
                let idleAmp: CGFloat = midY * 0.12
                // Voice amplitude — more aggressive scaling, no hard cap
                let voiceAmp: CGFloat = min(e * 8, 1.0) * midY * 0.85

                let points = stride(from: CGFloat(0), through: size.width, by: 1).map { (x: CGFloat) -> CGPoint in
                    let norm: CGFloat = x / size.width
                    // Idle: slow gentle wave always present
                    let idle: CGFloat = sin(norm * .pi * 2 + t * 2) * idleAmp
                    // Voice: multiple overlapping frequencies for organic feel
                    let w1: CGFloat = sin(norm * .pi * 4 + t * 8) * voiceAmp
                    let w2: CGFloat = sin(norm * .pi * 7 + t * 5.5) * voiceAmp * 0.5
                    let w3: CGFloat = sin(norm * .pi * 11 + t * 12) * voiceAmp * 0.2
                    return CGPoint(x: x, y: midY + idle + w1 + w2 + w3)
                }
                var path = Path()
                if let first = points.first {
                    path.move(to: first)
                    for pt in points.dropFirst() {
                        path.addLine(to: pt)
                    }
                }
                context.stroke(path, with: .color(color), lineWidth: lineWidth)
            }
        }
        .frame(width: width, height: height)
    }
}
