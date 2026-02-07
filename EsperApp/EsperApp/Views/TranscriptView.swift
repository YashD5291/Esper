import SwiftUI

struct TranscriptView: View {
    let sentences: [SentencePayload]
    let draftText: String

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(sentences.enumerated()), id: \.offset) { index, sentence in
                        Text(sentence.text)
                            .foregroundStyle(.primary)
                            .textSelection(.enabled)
                            .id("sentence-\(index)")
                    }

                    if !draftText.isEmpty {
                        Text(draftText)
                            .foregroundStyle(.secondary)
                            .id("draft")
                    }

                    if sentences.isEmpty && draftText.isEmpty {
                        Text("Transcription will appear here...")
                            .foregroundStyle(.tertiary)
                            .italic()
                    }

                    // Invisible anchor for scrolling
                    Color.clear
                        .frame(height: 1)
                        .id("bottom")
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
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
}
