// 主窗口：顶部是投递进度与常用按钮，下方内嵌控制台网页（WKWebView）。
// 控制台没跑时显示占位与「启动控制台」按钮。

import AppKit
import WebKit

final class MainWindowController: NSWindowController, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    private weak var actions: AppDelegate?
    private let statusLabel = NSTextField(labelWithString: "")
    private let progressLabel = NSTextField(labelWithString: "")
    private let webView = WKWebView()
    private let placeholder = NSStackView()
    private let placeholderLabel = NSTextField(labelWithString: "")
    private var buttonsNeedingConsole: [NSButton] = []
    private var backButton: NSButton!
    private var backObservation: NSKeyValueObservation?
    private var consoleAvailable = false
    private var loaded = false

    init(actions: AppDelegate) {
        self.actions = actions
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1200, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = "求职控制台"
        window.minSize = NSSize(width: 720, height: 480)
        window.isReleasedWhenClosed = false
        super.init(window: window)
        window.delegate = self
        if !window.setFrameUsingName("JobflowMainWindow") { window.center() }
        window.setFrameAutosaveName("JobflowMainWindow")
        buildContent()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    private func button(_ title: String, _ symbol: String, _ action: Selector, needsConsole: Bool) -> NSButton {
        let b = NSButton(title: title, image: NSImage(systemSymbolName: symbol, accessibilityDescription: nil)!,
                         target: nil, action: action)
        b.bezelStyle = .rounded
        b.imagePosition = .imageLeading
        if needsConsole { buttonsNeedingConsole.append(b) }
        return b
    }

    private func buildContent() {
        guard let content = window?.contentView, let actions else { return }

        statusLabel.font = .systemFont(ofSize: 13, weight: .medium)
        progressLabel.font = .systemFont(ofSize: 13)
        progressLabel.textColor = .secondaryLabelColor

        backButton = button("返回", "chevron.left", #selector(goBack), needsConsole: false)
        backButton.target = self
        backButton.keyEquivalent = "["
        backButton.keyEquivalentModifierMask = .command
        backButton.toolTip = "返回上一页（⌘[）"
        backButton.isEnabled = false

        let reload = button("刷新", "arrow.clockwise", #selector(reloadPage), needsConsole: true)
        reload.target = self
        let open = button("在浏览器打开", "safari", #selector(AppDelegate.openWeb), needsConsole: true)
        let copy = button("复制地址", "doc.on.doc", #selector(AppDelegate.copyWeb), needsConsole: true)
        let reports = button("报告文件夹", "folder", #selector(AppDelegate.openReports), needsConsole: false)
        [open, copy, reports].forEach { $0.target = actions }

        let spacer = NSView()
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let statusRow = NSStackView(views: [statusLabel, progressLabel])
        statusRow.spacing = 12
        let navigationRow = NSStackView(views: [backButton, reload, open, copy, reports, spacer])
        navigationRow.spacing = 12
        let bar = NSStackView(views: [statusRow, navigationRow])
        bar.orientation = .vertical
        bar.alignment = .leading
        bar.spacing = 8
        bar.edgeInsets = NSEdgeInsets(top: 10, left: 16, bottom: 10, right: 16)

        let divider = NSBox()
        divider.boxType = .separator

        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        // Observe history directly, including same-document navigation and back/forward changes.
        backObservation = webView.observe(\.canGoBack, options: [.initial, .new]) { [weak self] _, _ in
            self?.updateBackButton()
        }

        placeholderLabel.font = .systemFont(ofSize: 15)
        placeholderLabel.textColor = .secondaryLabelColor
        let start = NSButton(title: "启动控制台", target: actions, action: #selector(AppDelegate.startClicked))
        start.bezelStyle = .rounded
        start.keyEquivalent = "\r"
        placeholder.orientation = .vertical
        placeholder.spacing = 14
        placeholder.addArrangedSubview(placeholderLabel)
        placeholder.addArrangedSubview(start)

        for v in [bar, divider, webView, placeholder] as [NSView] {
            v.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(v)
        }
        NSLayoutConstraint.activate([
            bar.topAnchor.constraint(equalTo: content.topAnchor),
            bar.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            divider.topAnchor.constraint(equalTo: bar.bottomAnchor),
            divider.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            divider.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            webView.topAnchor.constraint(equalTo: divider.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            placeholder.centerXAnchor.constraint(equalTo: webView.centerXAnchor),
            placeholder.centerYAnchor.constraint(equalTo: webView.centerYAnchor),
        ])
    }

    func update(state: ServiceState, stateText: String, progress: Progress) {
        let up = state == .running || state == .external
        consoleAvailable = up
        updateBackButton()
        let color: NSColor = up ? .systemGreen : (state == .starting ? .systemOrange : .systemGray)
        let status = NSMutableAttributedString(string: "● ", attributes: [.foregroundColor: color])
        status.append(NSAttributedString(string: "控制台\(stateText)", attributes: [.foregroundColor: NSColor.labelColor]))
        statusLabel.attributedStringValue = status

        let count = progress.target.map { "\(progress.verified) / \($0)" } ?? "\(progress.verified)"
        var parts = ["已验证投递 \(count)", "待审核草稿 \(progress.pendingReviews)"]
        if progress.awaitingUser > 0 { parts.append("等你拍板 \(progress.awaitingUser)") }
        progressLabel.stringValue = parts.joined(separator: "  ·  ")

        buttonsNeedingConsole.forEach { $0.isEnabled = up }
        webView.isHidden = !up
        placeholder.isHidden = up
        placeholder.arrangedSubviews.last?.isHidden = state != .stopped
        placeholderLabel.stringValue = state == .starting ? "控制台启动中…" : "控制台没有运行"

        if up && !loaded {
            loaded = true
            webView.load(URLRequest(url: webURL))
        } else if !up {
            loaded = false
        }
    }

    @objc func reloadPage() { webView.reload() }

    private func updateBackButton() {
        backButton.isEnabled = consoleAvailable && webView.canGoBack
    }

    @objc func goBack() {
        guard consoleAvailable, webView.canGoBack else { return }
        webView.goBack()
    }

    // 控制台内的外部链接（如 JD 原链接）交给默认浏览器，本窗口只显示本机控制台。
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, let host = url.host, host != "127.0.0.1" && host != "localhost" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    // target=_blank / window.open：本机页面在本窗口打开，外部链接交给默认浏览器。
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if let host = url.host, host != "127.0.0.1" && host != "localhost" {
                NSWorkspace.shared.open(url)
            } else {
                webView.load(URLRequest(url: url))
            }
        }
        return nil
    }

    func windowWillClose(_ notification: Notification) {
        // 关窗后回到纯菜单栏形态，Dock 图标消失；服务继续跑。
        NSApp.setActivationPolicy(.accessory)
    }
}
