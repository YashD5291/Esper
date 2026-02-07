import Foundation

/// Spawns `python -m src.server` and manages JSON-line communication.
final class ProcessBridge: @unchecked Sendable {
    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private var readThread: Thread?

    private var eventContinuation: AsyncStream<ServerEvent>.Continuation?
    private(set) var isRunning = false
    private var userInitiatedStop = false

    /// Async stream of events from the Python process.
    let events: AsyncStream<ServerEvent>

    init() {
        var continuation: AsyncStream<ServerEvent>.Continuation!
        events = AsyncStream { continuation = $0 }
        eventContinuation = continuation
    }

    // MARK: - Lifecycle

    func launch(pythonPath: String, projectDir: String) {
        guard !isRunning else { return }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonPath)
        proc.arguments = ["-m", "src.server"]
        proc.currentDirectoryURL = URL(fileURLWithPath: projectDir)

        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        // Ensure the venv's bin is on PATH so Python finds its packages
        let venvBin = (projectDir as NSString).appendingPathComponent(".venv/bin")
        if let existingPath = env["PATH"] {
            env["PATH"] = "\(venvBin):\(existingPath)"
        } else {
            env["PATH"] = venvBin
        }
        proc.environment = env

        let stdin = Pipe()
        let stdout = Pipe()
        let stderr = Pipe()

        proc.standardInput = stdin
        proc.standardOutput = stdout
        proc.standardError = stderr

        stdinPipe = stdin
        stdoutPipe = stdout
        stderrPipe = stderr
        process = proc

        // Read stderr on a background queue (just log it)
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                for line in text.components(separatedBy: "\n") where !line.isEmpty {
                    print("[Python] \(line)")
                }
            }
        }

        // Handle process termination
        let continuation = eventContinuation
        userInitiatedStop = false
        proc.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                self?.isRunning = false
                let code = process.terminationStatus
                if code != 0, self?.userInitiatedStop != true {
                    continuation?.yield(.crashed(code))
                }
            }
        }

        do {
            try proc.run()
            isRunning = true
            startReading(stdout: stdout)
        } catch {
            eventContinuation?.yield(.error("Failed to launch Python: \(error.localizedDescription)"))
        }
    }

    func send(cmd: String, data: [String: Any]? = nil) {
        guard let pipe = stdinPipe, isRunning else { return }

        var obj: [String: Any] = ["cmd": cmd]
        if let data = data {
            obj["data"] = data
        }

        guard let jsonData = try? JSONSerialization.data(withJSONObject: obj),
              var jsonString = String(data: jsonData, encoding: .utf8) else {
            return
        }

        jsonString += "\n"
        if let writeData = jsonString.data(using: .utf8) {
            pipe.fileHandleForWriting.write(writeData)
        }
    }

    func terminate() {
        userInitiatedStop = true
        stdinPipe?.fileHandleForWriting.closeFile()
        process?.terminate()
        process = nil
        stdinPipe = nil
        stdoutPipe = nil
        stderrPipe = nil
        isRunning = false
    }

    // MARK: - Reading

    private func startReading(stdout: Pipe) {
        let handle = stdout.fileHandleForReading
        let continuation = eventContinuation
        let thread = Thread {
            var buffer = Data()
            let newline = UInt8(ascii: "\n")

            while true {
                let data = handle.availableData
                if data.isEmpty {
                    break
                }
                buffer.append(data)

                while let newlineIndex = buffer.firstIndex(of: newline) {
                    let lineData = buffer[buffer.startIndex..<newlineIndex]
                    buffer = buffer[buffer.index(after: newlineIndex)...]

                    if let event = ServerEvent.parse(json: Data(lineData)) {
                        continuation?.yield(event)
                    }
                }
            }

            continuation?.finish()
        }
        thread.name = "process-bridge-reader"
        thread.qualityOfService = .userInitiated
        thread.start()
        readThread = thread
    }
}
