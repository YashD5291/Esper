import Darwin
import Foundation

// Debug log to file (visible even from Launchpad launch)
let _debugLog: FileHandle? = {
    let path = "/tmp/esper-bridge.log"
    FileManager.default.createFile(atPath: path, contents: nil)
    return FileHandle(forWritingAtPath: path)
}()
func dlog(_ msg: String) {
    let line = "\(Date()) \(msg)\n"
    _debugLog?.seekToEndOfFile()
    _debugLog?.write(line.data(using: .utf8)!)
    NSLog("%@", msg)
}

/// Spawns `python -m src.server` and manages JSON-line communication.
final class ProcessBridge: @unchecked Sendable {
    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private var protocolPipe: Pipe?
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
        // When running from app bundle, set Python paths for embedded runtime
        if let resourcePath = Bundle.main.resourcePath {
            let sitePackages = (resourcePath as NSString).appendingPathComponent("site-packages")
            if FileManager.default.fileExists(atPath: sitePackages) {
                // Bundled mode: tell Python where to find packages and source
                let pythonHome = (resourcePath as NSString).appendingPathComponent("python")
                env["PYTHONHOME"] = pythonHome
                env["PYTHONPATH"] = "\(sitePackages):\(resourcePath)"
            }
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
        protocolPipe = stdout  // Protocol events come over stdout (all print() removed in Phase 2)
        process = proc

        // No --protocol-fd: Python falls back to stdout for protocol events.
        // macOS 26+ POSIX_SPAWN_CLOEXEC_DEFAULT closes extra fds despite fcntl.
        proc.arguments = ["-m", "src.server"]

        // Read stderr on a background queue (Python logging)
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                for line in text.components(separatedBy: "\n") where !line.isEmpty {
                    dlog("[Python] \(line)")
                }
            }
        }

        // Handle process termination
        let continuation = eventContinuation
        userInitiatedStop = false
        proc.terminationHandler = { [weak self] process in
            let code = process.terminationStatus
            dlog("[Bridge] Process terminated with code=\(code), userStop=\(self?.userInitiatedStop ?? false)")
            DispatchQueue.main.async {
                self?.isRunning = false
                if code != 0, self?.userInitiatedStop != true {
                    continuation?.yield(.crashed(code))
                }
            }
        }

        do {
            dlog("[Bridge] Launching: \(pythonPath) -m src.server, cwd=\(projectDir)")
            dlog("[Bridge] Env PYTHONHOME=\(env["PYTHONHOME"] ?? "nil")")
            try proc.run()
            isRunning = true
            dlog("[Bridge] Process running, pid=\(proc.processIdentifier), read fd=\(stdout.fileHandleForReading.fileDescriptor)")
            // Protocol events come over stdout — read from stdout pipe
            startReading(protocolPipe: stdout)
        } catch {
            stdin.fileHandleForWriting.closeFile()
            stdout.fileHandleForReading.closeFile()
            stderr.fileHandleForReading.closeFile()
            stdinPipe = nil
            stdoutPipe = nil
            stderrPipe = nil
            protocolPipe = nil
            process = nil
            eventContinuation?.yield(.error("Failed to launch Python: \(error.localizedDescription)"))
        }
    }

    func send(cmd: String, data: [String: Any]? = nil) {
        guard let pipe = stdinPipe, isRunning else {
            dlog("[Bridge] send(\(cmd)) DROPPED — pipe=\(stdinPipe != nil), running=\(isRunning)")
            return
        }

        var obj: [String: Any] = ["cmd": cmd]
        if let data = data {
            obj["data"] = data
        }

        guard let jsonData = try? JSONSerialization.data(withJSONObject: obj),
              var jsonString = String(data: jsonData, encoding: .utf8) else {
            return
        }

        dlog("[Bridge] send: \(jsonString.prefix(120))")
        jsonString += "\n"
        if let writeData = jsonString.data(using: .utf8) {
            pipe.fileHandleForWriting.write(writeData)
        }
    }

    func terminate() {
        userInitiatedStop = true
        stdinPipe?.fileHandleForWriting.closeFile()
        stdoutPipe?.fileHandleForReading.readabilityHandler = nil
        stderrPipe?.fileHandleForReading.readabilityHandler = nil
        process?.terminate()
        process = nil
        stdinPipe = nil
        stdoutPipe = nil
        stderrPipe = nil
        protocolPipe = nil
        isRunning = false
    }

    // MARK: - Reading

    private func startReading(protocolPipe: Pipe) {
        let handle = protocolPipe.fileHandleForReading
        let continuation = eventContinuation
        let thread = Thread {
            dlog("[Bridge] Reader thread started on fd=\(handle.fileDescriptor)")
            var buffer = Data()
            let newline = UInt8(ascii: "\n")

            while true {
                dlog("[Bridge] Reader: calling availableData on fd=\(handle.fileDescriptor)...")
                let data = handle.availableData
                if data.isEmpty {
                    dlog("[Bridge] Reader: EOF (0 bytes)")
                    break
                }
                dlog("[Bridge] Reader: got \(data.count) bytes")
                buffer.append(data)

                while let newlineIndex = buffer.firstIndex(of: newline) {
                    let lineData = buffer[buffer.startIndex..<newlineIndex]
                    buffer = buffer[buffer.index(after: newlineIndex)...]

                    let lineStr = String(data: Data(lineData), encoding: .utf8) ?? "<non-utf8>"
                    if let event = ServerEvent.parse(json: Data(lineData)) {
                        dlog("[Bridge] Parsed: \(lineStr.prefix(80))")
                        if continuation != nil {
                            continuation!.yield(event)
                        } else {
                            dlog("[Bridge] ERROR: continuation is nil!")
                        }
                    } else if !lineStr.isEmpty {
                        dlog("[Bridge] FAILED to parse: \(lineStr.prefix(120))")
                    }
                }
            }

            NSLog("[Bridge] Reader thread exiting")
            continuation?.finish()
        }
        thread.name = "process-bridge-reader"
        thread.qualityOfService = .userInitiated
        thread.start()
        readThread = thread
    }
}
