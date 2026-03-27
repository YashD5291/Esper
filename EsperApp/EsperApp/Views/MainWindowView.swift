import SwiftUI

struct MainWindowView: View {
    let engine: TranscriptionEngine

    var body: some View {
        VStack(spacing: 0) {
            headerBar

            AudioLevelMeter(level: engine.energyLevel)
                .padding(.horizontal, 16)
                .padding(.bottom, 8)

            Divider()

            TranscriptView(
                sentences: engine.sentences
            )

            Divider()

            controlBar
        }
        .frame(minWidth: 480, minHeight: 420)
    }

    // MARK: - Header

    private var headerBar: some View {
        HStack(spacing: 10) {
            StatusBadge(status: engine.status)

            Text(engine.status.displayName)
                .font(.headline)

            Spacer()

            if !engine.devices.isEmpty {
                Picker(selection: Binding(
                    get: { engine.selectedDevice ?? -1 },
                    set: { if $0 != -1 { engine.setDevice($0) } }
                )) {
                    ForEach(engine.devices) { device in
                        Text(device.name).tag(device.index)
                    }
                } label: {
                    Label("Input", systemImage: "mic")
                }
                .labelsHidden()
                .fixedSize()

                Button {
                    engine.refreshDevices()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .help("Refresh audio devices")
            }

            Text("WHISPER")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(.quaternary)
                .clipShape(Capsule())
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    // MARK: - Controls

    private var controlBar: some View {
        VStack(spacing: 8) {
            Button {
                if engine.status == .listening {
                    engine.stopListening()
                } else if engine.status == .idle {
                    engine.startListening()
                }
            } label: {
                HStack(spacing: 8) {
                    if engine.isLoading {
                        ProgressView()
                            .controlSize(.small)
                    }
                    Label(buttonLabel, systemImage: buttonIcon)
                }
                .frame(maxWidth: .infinity)
            }
            .controlSize(.large)
            .buttonStyle(.borderedProminent)
            .tint(engine.status == .listening ? .red : .accentColor)
            .disabled(engine.isLoading)

            if let error = engine.errorMessage {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.yellow)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)

                    Spacer()

                    Button("Restart") {
                        engine.restart()
                    }
                    .controlSize(.small)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    private var buttonLabel: String {
        switch engine.status {
        case .idle: "Start Listening"
        case .downloadingModel: "Downloading Model..."
        case .compilingShaders: "Compiling Shaders..."
        case .loadingModel: "Loading Model..."
        case .transcribing: "Transcribing..."
        case .listening: "Stop Listening"
        }
    }

    private var buttonIcon: String {
        switch engine.status {
        case .idle: "mic.fill"
        case .downloadingModel, .compilingShaders, .loadingModel: "hourglass"
        case .transcribing: "waveform"
        case .listening: "stop.fill"
        }
    }
}
