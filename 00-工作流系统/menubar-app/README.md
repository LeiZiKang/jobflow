# 求职控制台 · 菜单栏 App

原生 AppKit App（菜单栏常驻 + 主窗口），托管 `../local-control/start.sh`（jobflowd + Next.js 控制台），
不复制启动逻辑。安装在 `~/Applications/求职控制台.app`，构建产物不进工作树。

## 下载安装

支持 macOS 13+，同时支持 Apple Silicon 和 Intel。
从 [最新 Release 下载 Jobflow.dmg](https://github.com/LeiZiKang/jobflow/releases/latest/download/Jobflow.dmg)，
打开 DMG，把「求职控制台.app」拖进 Applications。无需自己编译 App。

App 使用 ad-hoc 签名，未经 Apple 公证。首次打开如果被 Gatekeeper 拦截，
到「系统设置 → 隐私与安全性」找到刚被拦截的 App，点击「仍要打开」，再确认打开。
较早的 macOS 也可在 Finder 中右键 App →「打开」。只对你信任的下载执行此操作。

DMG 仅包含菜单栏 App，不包含仓库、Node.js、Python 或控制台依赖。
先下载或 clone jobflow 仓库，按仓库新手指南准备 Python 3、Node.js 22 和工作区，
并在 `console/` 执行 `npm ci`。预编译 App 不需要 Swift 编译工具链；运行引擎仍需要上述环境。
首次启动会弹出文件夹选择器，选择包含 `00-工作流系统/local-control/start.sh` 的仓库根目录。
取消选择不会启动服务，可稍后通过「启动控制台」或「更换仓库文件夹…」重新选择。

路径按顺序取第一个有效值：`JOBFLOW_REPO` 环境变量 → UserDefaults 保存的路径 →
开发者构建写入 Info.plist 的 `JobflowRepo`。都无效时重新选择。
搬家后无需重新编译。在菜单里先停止控制台，再选「更换仓库文件夹…」，然后启动控制台。
显式设置的 `JOBFLOW_REPO` 在下次启动时仍有最高优先级。

## 开发者构建

需要 Xcode Command Line Tools（`xcode-select --install`）。

```bash
./00-工作流系统/menubar-app/build.sh
# 默认编译当前架构、ad-hoc 签名并覆盖安装到 ~/Applications/求职控制台.app
# 会先退出旧实例；JOBFLOW_MENUBAR_APP 可覆盖安装位置。

./00-工作流系统/menubar-app/build.sh --dmg /tmp/jf/Jobflow.dmg
# 分别编译 arm64 / x86_64，lipo 合并、签名并打包；不安装、不退出本机 App。
```

DMG 不嵌入构建机仓库路径，包含 App 和指向 `/Applications` 的快捷方式。
推送 `v*` 标签会运行 release workflow，创建同名 Release（若不存在），并上传固定资产名 `Jobflow.dmg`。

- 菜单栏显示 `已验证投递/目标`，数据与 `jobflow.py status` 同源（`state/current.json` 的 metrics），每 5 秒刷新。
- 菜单：控制台状态、待审核草稿数、打开控制台（`127.0.0.1:8788`，默认浏览器）、复制控制台地址（粘到任意浏览器）、
  打开 `05-检索报告`、启动 / 重启 / 停止、查看日志、开机自启动开关、退出。
- 主窗口：顶栏分两行显示控制台状态、投递进度与按钮（返回 / 刷新 / 在浏览器打开 / 复制地址 / 报告文件夹），下方 WKWebView 内嵌控制台；
  「返回」使用网页历史，可从报告回到原入口，快捷键为 `⌘[`；无上一页或服务未运行时置灰。
  外部链接交给默认浏览器。手动打开 App 或再次双击会显示主窗口；开机自启动时只进菜单栏。关窗不退出，Dock 图标随窗口出现/消失。
- 图标由 `make-icon.swift` 在构建时画出（深色底 + 公文包 + 绿色对勾），不提交二进制。
- 退出 App 会向 start.sh 整个进程组发 SIGTERM，start.sh 的 trap 清掉锁、pid 与 token。
- 开机自启动用 `SMAppService.mainApp`（系统设置 → 通用 → 登录项可见）。首次运行默认打开，之后以菜单开关为准。
  `JobflowMenu --login-status` 可在命令行查看状态。
- 日志：`~/.local/state/jobflow/menubar-console.log`。
- 如果控制台已被 `打开本地求职控制台.command` 启动，App 显示「由其他窗口启动」，不重复启动也不接管停止。
