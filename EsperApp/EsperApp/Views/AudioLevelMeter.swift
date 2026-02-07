import SwiftUI

struct AudioLevelMeter: View {
    let level: Double

    // Scale up raw RMS (speech is typically 0.01-0.3)
    private var displayLevel: Double {
        min(level * 3.0, 1.0)
    }

    private var meterColor: Color {
        if displayLevel < 0.5 {
            return .green
        } else if displayLevel < 0.8 {
            return .orange
        } else {
            return .red
        }
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                // Background track
                RoundedRectangle(cornerRadius: 2)
                    .fill(.quaternary)

                // Active level
                RoundedRectangle(cornerRadius: 2)
                    .fill(meterColor)
                    .frame(width: geo.size.width * displayLevel)
                    .animation(.linear(duration: 0.08), value: displayLevel)
            }
        }
        .frame(height: 4)
    }
}
