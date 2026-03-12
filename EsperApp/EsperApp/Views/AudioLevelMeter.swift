import SwiftUI

struct AudioLevelMeter: View {
    let level: Double

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
                RoundedRectangle(cornerRadius: 3)
                    .fill(.quaternary)

                RoundedRectangle(cornerRadius: 3)
                    .fill(meterColor.gradient)
                    .frame(width: geo.size.width * displayLevel)
                    .animation(.linear(duration: 0.08), value: displayLevel)
            }
        }
        .frame(height: 6)
    }
}
