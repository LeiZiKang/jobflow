# 菜单栏 App 签名与公证

默认使用 GitHub Actions 的 **Release DMG** 工作流完成签名、公证和上传。本机公证作为备用。
本文所有身份、团队、账户和 profile 都是占位符。真实值只由维护者保存到 GitHub Environment
secrets 或自己的钥匙串；不要写入源码、工作流、报告或普通日志。

## 云端一次性配置

在仓库 **Settings → Environments → release → Environment secrets** 设置以下六项。
名称固定，值由维护者自行填写；不要放到普通 Variables 中。

| Secret | 含义 |
|---|---|
| `MACOS_CERT_P12_BASE64` | Developer ID Application 证书与对应私钥导出的 `.p12` 文件，再进行 base64 编码 |
| `MACOS_CERT_PASSWORD` | 导出该 `.p12` 时设置的密码，必须非空 |
| `MACOS_SIGN_IDENTITY` | 完整签名身份名称，形如 `Developer ID Application: <Name> (<TEAMID>)` |
| `NOTARY_APPLE_ID` | 有权使用 Apple 公证服务的 Apple ID |
| `NOTARY_APP_PASSWORD` | 该 Apple ID 的 App 专用密码，不是登录密码 |
| `NOTARY_TEAM_ID` | 证书所属的 Apple Developer 团队 ID |

使用 **Developer ID Application**，不是 Apple Development、Mac Distribution 或 Developer ID Installer。
导出时必须带私钥；base64 只是编码，不是加密，导出文件和编码内容都按凭据保管。
维护者应检查 `release` Environment 的审批人、分支和标签规则，允许实际发版和手动运行的 ref。
Environment 保护规则通过后，job 才能读取 secrets。

六项全部非空才启用签名与公证。任一缺失会打印一行 notice，构建并上传 ad-hoc DMG，summary
写 `DMG: ad-hoc`。这也会替换已有公证附件，重建前务必确认配置完整。
配置齐全但证书导入、认证、签名或公证失败时，工作流失败，不降级、不上传。

工作流在 `$RUNNER_TEMP` 创建随机密码的临时钥匙串，导入证书、设置 codesign 私钥访问权限，
并加入现有搜索列表；随后非交互保存 `jobflow-ci` notary profile。凭据仅通过构建步骤的 `env`
注入，不打开 shell tracing，不输出导入及凭据保存命令的原始响应。
最后一个 `always()` 步骤删除临时钥匙串和 p12，即使构建或上传失败也执行。

## 云端发版与重建

源码的 `VERSION` 必须对应标签。正常发版由维护者执行：

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

推送 `v*` 标签会触发工作流，校验标签等于 `v$(cat VERSION)`。
构建通过后，Release 不存在则创建，再用 `gh release upload --clobber` 上传固定附件名
`Jobflow.dmg`；上传后下载附件并比较 SHA-256，不一致则 job 失败。
summary 写 `DMG: notarized` 或 `DMG: ad-hoc`，表示构建类型；上传及下载校验还须看 job 结果。

给已有 Release 重建：打开 **Actions → Release DMG → Run workflow**，选择包含此工作流更新的
分支（通常 `main`），在必填的 `tag` 输入目标标签，例如 `vX.Y.Z`，再运行。
工作流会 checkout `refs/tags/<tag>`，从该标签读 `VERSION` 并校验，构建该标签的源码，
不会把所选分支的 App 源码混入旧版本。也可由维护者运行：

```bash
gh workflow run release.yml --ref main -f tag=vX.Y.Z
```

默认分支须已包含 `workflow_dispatch` 定义，界面才可手动触发。
目标标签必须已存在，且其 `build.sh` 须支持 `JOBFLOW_NOTARY_KEYCHAIN` 才能使用此云端公证流程；
旧标签不会自动得到新脚本。相同目标标签的推送与手动任务共用并发组，避免同时覆盖同一附件。
如果仓库启用了 immutable releases，已发布附件可能不允许替换，`--clobber` 不能绕过该限制。

## 本机备用流程

1. 安装并选好 Xcode 命令行工具，确认 `swiftc`、`codesign`、`xcrun notarytool`、
   `xcrun stapler`、`gh` 可用。账户登录由维护者自行完成。
2. 把 Developer ID Application 证书及对应私钥安装到本机钥匙串。
3. 在自己的交互终端运行以下命令，按提示输入 Apple ID、团队 ID、App 专用密码。
   不在命令行写密码，不向 Agent 提供真实值，不打开 shell tracing。

   ```bash
   xcrun notarytool store-credentials '<NOTARY_PROFILE>'
   ```

确保源码对应目标标签、工作树干净，并等待该标签的云端任务结束后再运行：

```bash
JOBFLOW_SIGN_IDENTITY='Developer ID Application: <Name> (<TEAMID>)' \
JOBFLOW_NOTARY_PROFILE='<NOTARY_PROFILE>' \
./00-工作流系统/menubar-app/build.sh --dmg /tmp/Jobflow.dmg --notarize
# 仅在上一条退出码为 0 且验收通过后单独执行：
gh release upload vX.Y.Z /tmp/Jobflow.dmg --clobber
```

使用非默认钥匙串时，保存 profile 的命令增加 `--keychain '<KEYCHAIN_PATH>'`，构建时再设置
`JOBFLOW_NOTARY_KEYCHAIN='<KEYCHAIN_PATH>'`。未设置或为空时沿用默认钥匙串行为。
本机钥匙串解锁和授权弹窗由维护者处理；脚本只传 profile 名和可选路径，不读取凭据内容。
不要让本机上传与云端重建交错执行，后完成的上传会替换前一个附件。
若构建失败，输出位置已有的旧 DMG 保持不变，不能把旧文件误当成本次成功产物上传。

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
  云端核对 Environment secrets；本机继续用交互保存，不把密码交给构建脚本。
- **Invalid/Rejected、超时或网络失败**：使用脚本打印的 `log`/`history` 命令检查；
  退出码为 0 但状态不是 `Accepted` 也会失败。未创建提交时没有可取的日志，先修复认证/连接。
- **stapler / spctl 失败**：不要发布；核对是否确实 Accepted、服务是否可达、签名后是否改动内容。
  重新构建并公证，不关闭 Gatekeeper，也不增加宽泛 entitlement 来绕过问题。
- **沙箱中 hdiutil 失败**：这是本地镜像创建限制，可在普通维护者终端重试；不能据此声称签名或公证已通过。

依据：[Apple 公证流程](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)、
[Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)。

云端配置依据：[GitHub Environment secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)、
[GitHub Release 下载](https://cli.github.com/manual/gh_release_download)。
