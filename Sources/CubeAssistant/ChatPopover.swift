import AppKit

/// Speech-bubble popover: a prompt field and a scrolling reply area.
final class ChatViewController: NSViewController, NSTextFieldDelegate {
    var onSend: ((String) -> Void)?

    private let inputField = NSTextField()
    private let replyView = NSTextView()
    private let spinner = NSProgressIndicator()

    override func loadView() {
        let container = NSView(frame: NSRect(x: 0, y: 0, width: 320, height: 240))

        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false

        replyView.isEditable = false
        replyView.drawsBackground = false
        replyView.font = .systemFont(ofSize: 13)
        replyView.textContainerInset = NSSize(width: 6, height: 8)
        replyView.string = "Hi! Ask me anything ✨"
        replyView.autoresizingMask = [.width]
        replyView.isVerticallyResizable = true
        replyView.textContainer?.widthTracksTextView = true
        scroll.documentView = replyView

        inputField.translatesAutoresizingMaskIntoConstraints = false
        inputField.placeholderString = "Ask me anything…"
        inputField.font = .systemFont(ofSize: 13)
        inputField.delegate = self

        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false

        container.addSubview(scroll)
        container.addSubview(inputField)
        container.addSubview(spinner)

        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: container.topAnchor, constant: 10),
            scroll.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 10),
            scroll.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -10),
            scroll.bottomAnchor.constraint(equalTo: inputField.topAnchor, constant: -8),

            inputField.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 10),
            inputField.trailingAnchor.constraint(equalTo: spinner.leadingAnchor, constant: -8),
            inputField.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -10),

            spinner.centerYAnchor.constraint(equalTo: inputField.centerYAnchor),
            spinner.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -12),
            spinner.widthAnchor.constraint(equalToConstant: 16)
        ])

        view = container
    }

    func control(_ control: NSControl, textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
        if commandSelector == #selector(NSResponder.insertNewline(_:)) {
            let prompt = inputField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !prompt.isEmpty else { return true }
            inputField.stringValue = ""
            onSend?(prompt)
            return true
        }
        return false
    }

    func setBusy(_ busy: Bool) {
        inputField.isEnabled = !busy
        if busy {
            spinner.startAnimation(nil)
        } else {
            spinner.stopAnimation(nil)
            view.window?.makeFirstResponder(inputField)
        }
    }

    func showPrompt(_ prompt: String) {
        replyView.string = "You: \(prompt)\n\n…"
    }

    func showReply(_ reply: String, for prompt: String) {
        replyView.string = "You: \(prompt)\n\n\(reply)"
    }

    func showError(_ message: String) {
        replyView.string = "😵 \(message)"
    }

    func focusInput() {
        view.window?.makeFirstResponder(inputField)
    }

    func prefill(_ text: String) {
        loadViewIfNeeded()
        inputField.stringValue = text
    }
}
