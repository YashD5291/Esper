import SwiftUI

struct StatusBadge: View {
    let status: EngineStatus
    @State private var isPulsing = false

    private var color: Color {
        switch status {
        case .idle: .gray
        case .loadingModel: .orange
        case .listening: .green
        }
    }

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 10, height: 10)
            .shadow(color: color.opacity(status == .listening ? 0.6 : 0),
                    radius: isPulsing ? 6 : 3)
            .animation(
                status == .listening
                    ? .easeInOut(duration: 1.2).repeatForever(autoreverses: true)
                    : .default,
                value: isPulsing
            )
            .onChange(of: status) { _, newStatus in
                isPulsing = newStatus == .listening
            }
            .onAppear {
                isPulsing = status == .listening
            }
    }
}
