# 菜单栏 App 签名与公证

维护者在 macOS 本机执行。Actions 保持无证书构建，先挂 ad-hoc DMG；本机公证通过后才替换附件。
本文所有身份、团队、账户和 profile 都是占位符。不要把真实值、私钥或密码写入仓库、CI 或报告。

## 一次性准备

1. 安装 Xcode 并选好命令行工具，确认 `swiftc`、`codesign`、`xcrun notarytool`、
   `xcrun stapler`、`gh` 可用。安装与账户登录由维护者自行完成。
2. 在 Apple Developer 账户申请 **Developer ID Application** 证书，并将证书和对应私钥
   安装到本机钥匙串。不是 Apple Development、Mac Distribution 或 Developer ID Installer。
   用「钥匙串访问」确认完整名称为 `Developer ID Application: <Name> (<TEAMID>)`。
3. 维护者在自己的交互终端运行以下命令，按提示输入 Apple ID、团队 ID、App 专用密码。
   由 `notarytool` 直接保存到钥匙串，不向 Agent 提供这些值；不在命令行传密码、不打开 shell tracing。

   ```bash
   xcrun notarytool store-credentials '<NOTARY_PROFILE>'
   ```

   profile 是保存记录的名称，不是密码。脚本只把名称交给 `notarytool`，不读取凭据内容。
   不导出钥匙串，不自动修改私钥访问控制；解锁和授权弹窗由维护者处理。

## 每次发版

在仓库根目录执行，确保构建源码对应目标标签且工作树干净。版本号以 `VERSION` 为准。

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
# 等待该标签的 Release DMG workflow 完成，确认 Release 已挂 Jobflow.dmg（ad-hoc）。
# 本机使用该标签对应源码，再运行：
JOBFLOW_SIGN_IDENTITY='Developer ID Application: <Name> (<TEAMID>)' \
JOBFLOW_NOTARY_PROFILE='<NOTARY_PROFILE>' \
./00-工作流系统/menubar-app/build.sh --dmg /tmp/Jobflow.dmg --notarize
# 只有上一条退出码为 0 且本次验收完成，才单独执行上传：
gh release upload vX.Y.Z /tmp/Jobflow.dmg --clobber
```

等待 Actions 完成再上传，避免它随后把公证版覆盖成 ad-hoc。使用固定资产名 `Jobflow.dmg`。
若构建失败，输出位置已有的旧 DMG 保持不变，不能把旧文件误当成本次成功产物上传。
不要在替换后重新运行该标签的 Actions；如确需重跑，结束后重新上传已验收的公证版。

脚本按以下顺序执行（共两次公证提交，需要联网）：

1. 编译 universal 可执行文件，先签内部可执行文件，再签 `.app`，均启用 hardened runtime 和安全时间戳。
2. 将已签名 App 打成临时 ZIP，`notarytool submit --wait`，仅 `Accepted` 算成功。
3. 给 App 装订票据，再复制进 DMG；ZIP 不可装订票据，也不作为发布附件。
4. 用同一 Developer ID 身份签 DMG，提交 DMG 公证，成功后给 DMG 装订票据。
5. 验证 App 与 DMG 的签名、Gatekeeper 评估和装订票据，全部通过才将 DMG 移到输出路径。

选择先公证 ZIP 的原因：App 在进入只读压缩 DMG 前已有票据，无需挂载、修改和重新打包送审的 DMG。
App 与 DMG 都可携带离线票据；给 App 装订后不再重新签名。临时产物退出时清理。
失败时脚本打印 `notarytool log` 获取命令；没有提交 ID 时先用打印的 `history` 命令查找。
脚本不自动获取或输出日志，不展示服务原始响应。维护者自行检查日志，分享前脱敏。

## Entitlements 判断

当前 App **不启用 App Sandbox，也不添加 hardened runtime 例外**，因此没有 entitlements 文件：

- WKWebView 的网页执行由系统 WebKit 辅助进程负责，宿主不直接创建 JIT 可执行内存。
  不需要给宿主 `allow-jit`、`allow-unsigned-executable-memory` 或 `disable-library-validation`。
- 访问 `127.0.0.1` 不因 hardened runtime 需要网络 entitlement；`network.client` 属于 App Sandbox。
  现有 Info.plist 的本地网络 ATS 配置保留，ATS 与代码签名是两件事。
- `posix_spawn` 启动 `/bin/bash` 执行仓库脚本，不把子进程代码加载进宿主；无需运行时例外或 sandbox inherit。
  Node/Python 是独立进程，其运行条件不由宿主 entitlement 代替。
- `SMAppService.mainApp` 注册当前 App 为登录项，不需要额外 hardened runtime entitlement；
  系统登录项授权仍由用户控制。

这是对当前源码的判断；后续若引入进程内 JIT、第三方动态库或 Sandbox，必须重新评估。
签名和公证通过不代替功能测试，实际证书验收时仍需测试网页加载、启动/停止子进程和登录项。

## 验证

脚本对所有构建执行 `codesign --verify --strict --deep`。`--deep` 仅用于验证，不用于签名。
只设签名身份而不加 `--notarize` 时，生成已签名但未公证的 DMG，不运行必然缺票据的公证检查。
完全不设签名变量时仍是 ad-hoc，不执行网络时间戳、公证、Gatekeeper 或票据检查。

无需证书或联网的流程回归测试：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 00-工作流系统/menubar-app/test_build.py
```

测试用桩替代编译、签名、公证和镜像工具，验证参数、顺序、失败处理及输出保护，
不能作为真实 Apple 审核、DMG 可挂载或 Gatekeeper 放行的证据。

维护者挂载最终 DMG 后再次检查发布包内的 App（以下卷名对应脚本）：

```bash
hdiutil attach /tmp/Jobflow.dmg -readonly
codesign --verify --strict --deep '/Volumes/Jobflow/求职控制台.app'
codesign --verify --strict /tmp/Jobflow.dmg
spctl -a -vvv -t exec '/Volumes/Jobflow/求职控制台.app'
spctl -a -vvv -t open --context context:primary-signature /tmp/Jobflow.dmg
xcrun stapler validate '/Volumes/Jobflow/求职控制台.app'
xcrun stapler validate /tmp/Jobflow.dmg
hdiutil detach /Volumes/Jobflow
```

每条命令都应成功。最后在未放行过此 App 的 Mac/测试账户上，通过浏览器下载 Release 附件，
拖入 Applications，验证正常启动及上述功能；保留下载隔离属性，勿用移除 quarantine 代替验收。
公证版应无「无法验证开发者」提示，普通互联网下载确认提示仍可能出现。

## 常见失败

- **身份不存在/签名失败**：检查完整证书名称、有效期、对应私钥和钥匙串解锁状态；脚本不退回 ad-hoc。
  同时检查安全时间戳服务是否可达。
- **缺少 profile/签名身份**：`--notarize` 在编译前失败；设置两个环境变量，不能公证 ad-hoc。
- **profile 找不到、认证失败**：在维护者自己的终端重新运行 `store-credentials`，核对账户和团队。
  不把密码交给脚本或写入环境变量。
- **Invalid/Rejected、超时或网络失败**：使用脚本打印的 `log`/`history` 命令检查；
  退出码为 0 但状态不是 `Accepted` 也会失败。未创建提交时没有可取的日志，先修复认证/连接。
- **stapler / spctl 失败**：不要发布；核对是否确实 Accepted、服务是否可达、签名后是否改动内容。
  重新构建并公证，不关闭 Gatekeeper，也不增加宽泛 entitlement 来绕过问题。
- **沙箱中 hdiutil 失败**：这是本地镜像创建限制，可在普通维护者终端重试；不能据此声称签名或公证已通过。

依据：[Apple 公证流程](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)、
[Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)。
