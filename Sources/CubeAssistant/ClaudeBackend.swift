import Foundation

enum BackendError: LocalizedError {
    case binaryNotFound
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .binaryNotFound:
            return "Couldn't find the `claude` CLI. Install Claude Code or make sure it's on your PATH."
        case .failed(let message):
            return message.isEmpty ? "Claude exited with an error." : message
        }
    }
}

/// Shells out to the Claude Code CLI in non-interactive mode (`claude -p`).
final class ClaudeBackend {
    private lazy var binaryPath: String? = Self.findBinary()

    func send(_ prompt: String, completion: @escaping (Result<String, Error>) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let binary = self?.binaryPath else {
                DispatchQueue.main.async { completion(.failure(BackendError.binaryNotFound)) }
                return
            }

            let process = Process()
            process.executableURL = URL(fileURLWithPath: binary)
            process.arguments = ["-p", prompt, "--output-format", "text"]

            var environment = ProcessInfo.processInfo.environment
            let extraPaths = "/opt/homebrew/bin:/usr/local/bin"
            environment["PATH"] = [environment["PATH"], extraPaths].compactMap { $0 }.joined(separator: ":")
            process.environment = environment

            let stdout = Pipe()
            let stderr = Pipe()
            process.standardOutput = stdout
            process.standardError = stderr
            process.standardInput = FileHandle.nullDevice

            do {
                try process.run()
            } catch {
                DispatchQueue.main.async { completion(.failure(error)) }
                return
            }

            let outData = stdout.fileHandleForReading.readDataToEndOfFile()
            let errData = stderr.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()

            let output = String(data: outData, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let errorOutput = String(data: errData, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

            DispatchQueue.main.async {
                if process.terminationStatus == 0 {
                    completion(.success(output))
                } else {
                    completion(.failure(BackendError.failed(errorOutput.isEmpty ? output : errorOutput)))
                }
            }
        }
    }

    private static func findBinary() -> String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let candidates = [
            "\(home)/.claude/local/claude",
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
            "\(home)/.local/bin/claude"
        ]
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            return path
        }

        // GUI apps don't get a login-shell PATH; ask zsh where claude lives.
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", "which claude"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let path = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if process.terminationStatus == 0, !path.isEmpty,
               FileManager.default.isExecutableFile(atPath: path) {
                return path
            }
        } catch {}
        return nil
    }
}
