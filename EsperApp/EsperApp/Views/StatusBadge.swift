import SwiftUI

struct StatusBadge: View {
    let status: EngineStatus

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
            .frame(width: 8, height: 8)
            .shadow(color: color.opacity(status == .listening ? 0.6 : 0), radius: 4)
    }
}
