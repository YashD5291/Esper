import SwiftUI

struct TranscriptOverlayView: View {
    let lines: [String]
    let fontSize: CGFloat
    let textColor: Color
    let opacity: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(lines.enumerated()), id: \.element) { index, line in
                Text(line)
                    .font(.system(size: fontSize, weight: .medium, design: .rounded))
                    .foregroundStyle(textColor)
                    .shadow(color: .black.opacity(0.7), radius: 2, x: 1, y: 1)
                    .opacity(lineOpacity(index: index, total: lines.count))
            }
        }
        .opacity(opacity)
        .padding(.horizontal, 28)
        .padding(.vertical, 16)
        .frame(width: 660, alignment: .leading)
        .background(Color.clear)
    }

    private func lineOpacity(index: Int, total: Int) -> Double {
        guard total > 1 else { return 1.0 }
        let position = Double(total - 1 - index) / Double(total - 1)
        // Oldest line dims to 0.45, newest is 1.0
        return 0.45 + 0.55 * (1.0 - position)
    }
}
