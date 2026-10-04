# 求职控制台 · 菜单栏 App

原生 AppKit App（菜单栏常驻 + 主窗口），托管 `../local-control/start.sh`（jobflowd + Next.js 控制台），
不复制启动逻辑。安装在 `~/Applications/求职控制台.app`，构建产物不进工作树。

```bash
./00-工作流系统/menubar-app/build.sh   # 编译、ad-hoc 签名、覆盖安装（会先退出旧实例）
```

只支持 macOS 13+，需要 Xcode Command Line Tools（`xcode-select --install`）。
编译时会把**当前仓库路径**写进 App 的 Info.plist（`JobflowRepo`），所以仓库搬家后要重新运行一次 `build.sh`；
临时指向别的仓库可以设环境变量 `JOBFLOW_REPO`。App 是 ad-hoc 签名，只适合在本机自己编译自己用，不要分发二进制。
首次运行前先在 `console/` 里执行一次 `npm install`。

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
