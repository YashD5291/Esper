import SwiftUI

struct TranscriptView: View {
    let sentences: [SentencePayload]
    let draftText: String

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(sentences.enumerated()), id: \.offset) { index, sentence in
                        Text(sentence.text)
                            .textSelection(.enabled)
                            .id("sentence-\(index)")
                    }

                    if !draftText.isEmpty {
                        Text(draftText)
                            .foregroundStyle(.secondary)
                            .id("draft")
                    }

                    if sentences.isEmpty && draftText.isEmpty {
                        emptyState
                    }

                    Color.clear
                        .frame(height: 1)
                        .id("bottom")
                }
                .padding(16)
            }
            .onChange(of: sentences.count) {
                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
            .onChange(of: draftText) {
                proxy.scrollTo("bottom", anchor: .bottom)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "waveform")
                .font(.system(size: 32))
                .foregroundStyle(.quaternary)
            Text("Transcription will appear here")
                .font(.subheadline)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 60)
    }
}
