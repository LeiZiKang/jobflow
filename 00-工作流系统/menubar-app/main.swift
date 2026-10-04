// 求职控制台 · 菜单栏 App
//
// 只做三件事：托管 local-control/start.sh（jobflowd + Next.js 控制台）、在菜单栏显示
// 投递进度与端口、管理开机自启动（SMAppService，登录项里可见）。
// 启动逻辑仍以 start.sh 为唯一来源，本 App 不复制它的任何步骤。

import AppKit
import ServiceManagement

let home = FileManager.default.homeDirectoryForCurrentUser.path
let env = ProcessInfo.processInfo.environment
// 按优先级选第一个有效仓库；分发版不嵌入构建机路径。
func validRepository(_ path: String) -> Bool {
    var isDirectory: ObjCBool = false
    let script = "\(path)/00-工作流系统/local-control/start.sh"
    return !path.isEmpty && path.hasPrefix("/")
        && FileManager.default.fileExists(atPath: script, isDirectory: &isDirectory)
        && !isDirectory.boolValue && FileManager.default.isReadableFile(atPath: script)
}

var repoDir = [env["JOBFLOW_REPO"], UserDefaults.standard.string(forKey: "JobflowRepo"),
               Bundle.main.object(forInfoDictionaryKey: "JobflowRepo") as? String]
    .compactMap { $0 }.first(where: validRepository) ?? ""
let runtimeDir = NSString(string: env["JOBFLOW_RUNTIME_DIR"] ?? "\(env["XDG_STATE_HOME"] ?? "\(home)/.local/state")/jobflow").expandingTildeInPath
let webPort = env["JOBFLOW_WEB_PORT"] ?? "8788"
let webURL = URL(string: "http://127.0.0.1:\(webPort)/")!
var startScript: String { "\(repoDir)/00-工作流系统/local-control/start.sh" }
let logPath = "\(runtimeDir)/menubar-console.log"

enum ServiceState { case stopped, starting, running, external }

final class ConsoleProcess {
    private(set) var pid: pid_t = 0
    var onExit: ((Int32) -> Void)?

    var isAlive: Bool { pid > 0 && kill(pid, 0) == 0 }

    func start() throws {
        try FileManager.default.createDirectory(atPath: runtimeDir, withIntermediateDirectories: true)
        var attr: posix_spawnattr_t?
        posix_spawnattr_init(&attr)
        defer { posix_spawnattr_destroy(&attr) }
        // 独立进程组：停止时向整组发信号，next dev 与 jobflowd 一起退出，start.sh 的 trap 负责清锁。
        posix_spawnattr_setflags(&attr, Int16(POSIX_SPAWN_SETPGROUP))
        posix_spawnattr_setpgroup(&attr, 0)

        var actions: posix_spawn_file_actions_t?
        posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0)
        posix_spawn_file_actions_addopen(&actions, 1, logPath, O_WRONLY | O_CREAT | O_TRUNC, 0o644)
        posix_spawn_file_actions_adddup2(&actions, 1, 2)

        var childEnv = env
        // 从 Finder / 登录项启动时 PATH 很短，找不到 Homebrew 的 node 与 python3。
        childEnv["PATH"] = "\(home)/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        childEnv["JOBFLOW_CONSOLE_BROWSER"] = "none"
        let envStrings = childEnv.map { "\($0.key)=\($0.value)" }

        let args = ["/bin/bash", startScript]
        var cArgs = args.map { strdup($0) } + [nil]
        var cEnv = envStrings.map { strdup($0) } + [nil]
        defer { (cArgs + cEnv).forEach { free($0) } }

        var newPid: pid_t = 0
        let rc = posix_spawn(&newPid, "/bin/bash", &actions, &attr, &cArgs, &cEnv)
        guard rc == 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(rc)) }
        pid = newPid

        let watched = newPid
        DispatchQueue.global().async { [weak self] in
            var status: Int32 = 0
            waitpid(watched, &status, 0)
            DispatchQueue.main.async {
                guard let self, self.pid == watched else { return }
                self.pid = 0
                self.onExit?(status)
            }
        }
    }

    func stop() {
        guard pid > 0 else { return }
        let group = pid
        kill(-group, SIGTERM)
        DispatchQueue.global().asyncAfter(deadline: .now() + 6) {
            if kill(-group, 0) == 0 { kill(-group, SIGKILL) }
        }
    }
}

struct Progress {
    var verified = 0
    var target: Int? = nil
    var pendingReviews = 0
    var awaitingUser = 0
}

func loadProgress() -> Progress {
    var p = Progress()
    guard validRepository(repoDir) else { return p }
    let state = "\(repoDir)/00-工作流系统/state"
    func json(_ name: String) -> [String: Any]? {
        guard let data = FileManager.default.contents(atPath: "\(state)/\(name)") else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
    // 与 `jobflow.py status` 同源：current.json 的 metrics。
    let metrics = json("current.json")?["metrics"] as? [String: Any]
    p.verified = metrics?["submitted_verified"] as? Int ?? 0
    p.target = metrics?["diagnostic_sample_target"] as? Int
    if let tasks = json("task_queue.json")?["tasks"] as? [[String: Any]] {
        for t in tasks {
            let status = t["status"] as? String
            let title = t["title"] as? String ?? ""
            if status == "pending" && title.hasPrefix("审核草稿") { p.pendingReviews += 1 }
            if status == "waiting_user" { p.awaitingUser += 1 }
        }
    }
    return p
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let console = ConsoleProcess()
    var state: ServiceState = .stopped
    var progress = Progress()
    var wantRunning = true
    var timer: Timer?
    var updateTimer: Timer?
    var updateVersion: String?
    var updateURL: URL?

    func loadUpdateCache() {
        updateVersion = nil
        updateURL = nil
        guard env["JOBFLOW_UPDATE_CHECK"] != "0",
              let data = FileManager.default.contents(atPath: "\(runtimeDir)/update-check.json"),
              let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              value["status"] as? String == "ok",
              value["repository"] as? String == (env["JOBFLOW_UPDATE_REPO"] ?? "LeiZiKang/jobflow"),
              value["update_available"] as? Bool == true,
              let checked = value["checked_at"] as? Double,
              Date().timeIntervalSince1970 - checked >= 0,
              Date().timeIntervalSince1970 - checked < 24 * 60 * 60,
              let latest = value["latest_version"] as? String,
              let current = try? String(contentsOfFile: "\(repoDir)/VERSION", encoding: .utf8),
              current.trimmingCharacters(in: .whitespacesAndNewlines) == value["current_version"] as? String,
              latest.range(of: #"^\d+\.\d+\.\d+$"#, options: .regularExpression) != nil,
              let link = value["release_url"] as? String,
              link == "https://github.com/\(env["JOBFLOW_UPDATE_REPO"] ?? "LeiZiKang/jobflow")/releases/tag/v\(latest)",
              let url = URL(string: link) else { return }
        updateVersion = latest
        updateURL = url
    }

    @objc func openUpdateRelease() {
        if let url = updateURL { NSWorkspace.shared.open(url) }
    }

    var mainWindow: MainWindowController?
    var launchedAsLoginItem = false

    func applicationWillFinishLaunching(_ notification: Notification) {
        // 开机自启动时只进菜单栏，不弹主窗口；手动打开 App 才显示主窗口。
        if let event = NSAppleEventManager.shared().currentAppleEvent,
           event.eventID == kAEOpenApplication,
           event.paramDescriptor(forKeyword: keyAEPropData)?.enumCodeValue == keyAELaunchedAsLogInItem {
            launchedAsLoginItem = true
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem.button?.image = NSImage(systemSymbolName: "briefcase", accessibilityDescription: "求职控制台")
        statusItem.button?.imagePosition = .imageLeading
        let menu = NSMenu()
        menu.delegate = self
        statusItem.menu = menu

        // 首次运行默认打开开机自启动；之后以用户在菜单里的选择为准，不再自动改回。
        let key = "loginItemInitialized"
        if !UserDefaults.standard.bool(forKey: key) {
            try? SMAppService.mainApp.register()
            UserDefaults.standard.set(true, forKey: key)
        }

        console.onExit = { [weak self] _ in self?.poll() }
        if !validRepository(repoDir) { selectRepository() }
        progress = loadProgress()
        if validRepository(repoDir) { startService() }
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
        loadUpdateCache()
        updateTimer = Timer.scheduledTimer(withTimeInterval: 24 * 60 * 60, repeats: true) { [weak self] _ in self?.loadUpdateCache() }
        poll()
        NSApp.mainMenu = buildMainMenu()
        if !launchedAsLoginItem { showMainWindow() }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showMainWindow()
        return false
    }

    // 关掉主窗口不退出：服务继续跑，菜单栏图标还在。
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    @objc func showMainWindow() {
        if mainWindow == nil { mainWindow = MainWindowController(actions: self) }
        NSApp.setActivationPolicy(.regular)
        render()
        mainWindow?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func buildMainMenu() -> NSMenu {
        let main = NSMenu()
        func submenu(_ title: String, _ items: [NSMenuItem]) {
            let holder = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            let m = NSMenu(title: title)
            items.forEach { m.addItem($0) }
            holder.submenu = m
            main.addItem(holder)
        }
        func std(_ title: String, _ action: String, _ key: String) -> NSMenuItem {
            NSMenuItem(title: title, action: Selector(action), keyEquivalent: key)
        }
        submenu("求职控制台", [
            std("关于求职控制台", "orderFrontStandardAboutPanel:", ""),
            .separator(),
            std("隐藏求职控制台", "hide:", "h"),
            item("退出（同时停止控制台）", #selector(quit), "q"),
        ])
        submenu("编辑", [
            std("撤销", "undo:", "z"), std("重做", "redo:", "Z"), .separator(),
            std("剪切", "cut:", "x"), std("拷贝", "copy:", "c"), std("粘贴", "paste:", "v"),
            std("全选", "selectAll:", "a"),
        ])
        submenu("显示", [
            item("刷新控制台", #selector(reloadMainWindow), "r"),
        ])
        submenu("窗口", [
            std("最小化", "performMiniaturize:", "m"),
            std("关闭窗口", "performClose:", "w"),
        ])
        submenu("帮助", [
            item("使用说明", #selector(openGuide)),
        ])
        return main
    }

    @objc func reloadMainWindow() { mainWindow?.reloadPage() }

    func applicationWillTerminate(_ notification: Notification) {
        console.stop()
        // 给 start.sh 的 trap 一点时间清理锁与 token。
        let deadline = Date().addingTimeInterval(3)
        while console.isAlive && Date() < deadline { usleep(100_000) }
    }

    // MARK: service

    func startService() {
        guard validRepository(repoDir) else {
            selectRepository()
            guard validRepository(repoDir) else { return }
            startService()
            return
        }
        wantRunning = true
        guard !console.isAlive else { return }
        do {
            try console.start()
            state = .starting
        } catch {
            state = .stopped
            alert("启动失败", "\(error.localizedDescription)\n\n日志：\(logPath)")
        }
        render()
    }

    @objc func stopService() {
        wantRunning = false
        console.stop()
        state = .stopped
        render()
    }

    @objc func restartService() {
        console.stop()
        DispatchQueue.global().async { [weak self] in
            let deadline = Date().addingTimeInterval(8)
            while (self?.console.isAlive ?? false) && Date() < deadline { usleep(200_000) }
            DispatchQueue.main.async { self?.startService() }
        }
    }

    @objc func startClicked() { startService() }

    func poll() {
        progress = loadProgress()
        var req = URLRequest(url: webURL, timeoutInterval: 3)
        req.httpMethod = "HEAD"
        URLSession.shared.dataTask(with: req) { [weak self] _, resp, _ in
            let up = (resp as? HTTPURLResponse) != nil
            DispatchQueue.main.async {
                guard let self else { return }
                if up {
                    self.state = self.console.isAlive ? .running : .external
                } else if self.console.isAlive {
                    self.state = .starting
                } else {
                    self.state = .stopped
                }
                self.render()
            }
        }.resume()
    }

    // MARK: UI

    func render() {
        guard let button = statusItem.button else { return }
        let count = progress.target.map { "\(progress.verified)/\($0)" } ?? "\(progress.verified)"
        switch state {
        case .running, .external:
            button.title = " \(count)"
            button.appearsDisabled = false
        case .starting:
            button.title = " \(count) …"
            button.appearsDisabled = false
        case .stopped:
            button.title = " \(count)"
            button.appearsDisabled = true
        }
        button.toolTip = "已验证投递 \(count) · 控制台\(stateText)"
        mainWindow?.update(state: state, stateText: stateText, progress: progress)
    }

    var stateText: String {
        switch state {
        case .running: return "运行中"
        case .external: return "运行中（由其他窗口启动）"
        case .starting: return "启动中…"
        case .stopped: return "已停止"
        }
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        loadUpdateCache()
        menu.removeAllItems()
        if let latest = updateVersion {
            menu.addItem(item("有新版本 v\(latest)…", #selector(openUpdateRelease)))
            menu.addItem(.separator())
        }
        menu.addItem(item("打开主窗口", #selector(showMainWindow), "n"))
        menu.addItem(.separator())
        menu.addItem(info("控制台：\(stateText)"))
        let count = progress.target.map { "\(progress.verified) / \($0)" } ?? "\(progress.verified)"
        menu.addItem(info("已验证投递 \(count)"))
        menu.addItem(info("待审核草稿 \(progress.pendingReviews) 个"))
        if progress.awaitingUser > 0 { menu.addItem(info("等你拍板 \(progress.awaitingUser) 项")) }
        menu.addItem(.separator())

        let up = state == .running || state == .external
        let web = item("打开控制台  127.0.0.1:\(webPort)", #selector(openWeb), "o")
        web.isEnabled = up
        menu.addItem(web)
        let copy = item("复制控制台地址", #selector(copyWeb), "c")
        copy.isEnabled = up
        menu.addItem(copy)
        menu.addItem(item("打开报告文件夹", #selector(openReports), "r"))
        menu.addItem(.separator())

        switch state {
        case .stopped: menu.addItem(item("启动控制台", #selector(startClicked), "s"))
        case .external: menu.addItem(info("由其他窗口启动，请在那里停止"))
        case .running, .starting:
            menu.addItem(item("重启控制台", #selector(restartService)))
            menu.addItem(item("停止控制台", #selector(stopService)))
        }
        menu.addItem(item("更换仓库文件夹…", #selector(changeRepository)))
        menu.addItem(item("查看日志", #selector(openLog)))
        menu.addItem(item("使用说明", #selector(openGuide)))
        menu.addItem(.separator())

        let login = item("开机自启动", #selector(toggleLogin))
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        menu.addItem(login)
        menu.addItem(item("退出（同时停止控制台）", #selector(quit), "q"))
    }

    func info(_ title: String) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        i.isEnabled = false
        return i
    }

    func item(_ title: String, _ action: Selector, _ key: String = "") -> NSMenuItem {
        let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
        i.target = self
        return i
    }

    // 只允许在当前服务停止后切换，避免旧进程仍占用同一端口。
    @objc func changeRepository() {
        guard !console.isAlive && state == .stopped else {
            alert("请先停止控制台", "在菜单里停止控制台后再更换仓库；由其他窗口启动的服务需在那里停止。")
            return
        }
        selectRepository()
        progress = loadProgress()
        render()
    }

    func selectRepository() {
        NSApp.activate(ignoringOtherApps: true)
        let panel = NSOpenPanel()
        panel.title = "选择 jobflow 仓库文件夹"
        panel.message = "请选择包含 00-工作流系统/local-control/start.sh 的 jobflow 文件夹。"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = false
        while panel.runModal() == .OK {
            guard let url = panel.url, validRepository(url.path) else {
                alert("这不是 jobflow 仓库", "所选文件夹需要包含 00-工作流系统/local-control/start.sh。")
                continue
            }
            repoDir = url.path
            UserDefaults.standard.set(repoDir, forKey: "JobflowRepo")
            return
        }
    }

    @objc func openWeb() { NSWorkspace.shared.open(webURL) }

    @objc func copyWeb() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(webURL.absoluteString, forType: .string)
    }

    @objc func openReports() {
        guard validRepository(repoDir) else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: "\(repoDir)/05-检索报告"))
    }

    @objc func openGuide() {
        guard validRepository(repoDir) else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: "\(repoDir)/使用说明.html"))
    }

    @objc func openLog() {
        NSWorkspace.shared.open(URL(fileURLWithPath: logPath))
    }

    @objc func toggleLogin() {
        let service = SMAppService.mainApp
        do {
            if service.status == .enabled {
                try service.unregister()
            } else {
                try service.register()
            }
        } catch {
            alert("开机自启动设置失败", "\(error.localizedDescription)\n可在「系统设置 → 通用 → 登录项」手动添加。")
        }
        if service.status == .requiresApproval {
            alert("需要在系统设置里允许", "请到「系统设置 → 通用 → 登录项」打开「求职控制台」。")
            SMAppService.openSystemSettingsLoginItems()
        }
    }

    @objc func quit() { NSApp.terminate(nil) }

    func alert(_ title: String, _ text: String) {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = title
        a.informativeText = text
        a.runModal()
    }
}

if CommandLine.arguments.contains("--login-status") {
    let s = SMAppService.mainApp.status
    print([SMAppService.Status.notRegistered: "notRegistered", .enabled: "enabled",
           .requiresApproval: "requiresApproval", .notFound: "notFound"][s] ?? "unknown")
    exit(0)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
