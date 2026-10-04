# 主动联系日报本地接口

author: codex

仅从给定 JSON 生成私人只读 HTML；不会读取平台、邮箱、凭据或修改 canonical state。
示例完全虚构，不代表任何平台已连接或已检查。

```bash
python3 00-工作流系统/bin/inbound_digest.py --input 00-工作流系统/examples/inbound/daily-observation.json --validate
python3 00-工作流系统/bin/inbound_digest.py --input /private/tmp/actual-inbound-observation.json --output-dir 05-检索报告/inbound巡检
```

输入必需字段：

- `date`：严格 `YYYY-MM-DD`，用作日报名。
- `window`：`{start,end}`，带时区的 ISO 8601 时间；每条消息必须在此窗口内。
- `required_sources`：本轮必须巡检的授权渠道 ID 清单，必填非空。缺少渠道记录会补成 `not_checked`，整轮不能完成。
- `sources`：每个来源一条 `{source_id,status,observed_at,evidence_ref,reason,counts}`。
- `items`：消息数组，可为空。

`source_id` 支持 boss / liepin / linkedin / indeed / 51job / official_ats / email / slack 和自定义字符串。
`status` 支持 ok / empty / login_required / captcha_blocked / approval_blocked / unavailable / not_supported / not_checked。
ok / empty 必须有 `observed_at` 和 `evidence_ref`；其他状态必须有 `reason`，不能填 counts（未知不能写 0）。
`counts` 可省略，提供时必须与去重后消息分类完全一致，值为非负整数。
empty 指没有入站消息，不能与新联系、已投回复、自动确认或未知发送方并存。

每条 item 必须提供 `source_id, sender_role, received_at, summary, kind, source_ref`。
可选 `id, company, contact, role, recommendation, action_needed, application_id`（字符串）。
`sender_role` 为 self / recruiter / employer / unknown / system；`kind` 为 new_contact / application_reply / automatic_confirmation / promotion。
self 与 promotion 都不计入；unknown 单列待确认并使覆盖状态未完成；system 只允许自动确认或推广。
已投递后的回复与自动确认单列，不能当新主动联系。计数单位是消息，不能解释成独立联系人。

去重：同渠道同 id 合并完全一致记录，矛盾记录报错；无 id 时按完整规范化内容指纹保守去重。
不同渠道不自动合并同一人。时间窗口使用双端包含；相邻日报的边界消息可能同时展示，不要直接跨日报相加。
来源不完整时总数显示“至少 N”，受阻来源显示“—（未查全）”，仍保留已取得的部分消息。
CLI 不替采集器证明平台已全部读完：只有明确完成当前窗口回读时才可填 ok / empty。

证据引用只允许不带用户名密码的 http(s) URL，或无 `..`、控制字符、反斜杠和 URL scheme 的本地路径。
相对路径**相对于生成后的报告目录**，采集器应自行正确计算；此工具不验证证据文件存在与真实性。
正文全部转义，无 JavaScript、表单和远程资源，CSP 禁止主动网络请求。默认深色，适配手机与打印。

输出 `<date>.html` 和 `index.html`；索引扫描工具自己生成的日期报告，保留历史。不触碰既有 `汇总.html`。
同日重跑应输入完整当日观察；重建同日报告，不自动混入旧证据。未知格式现有文件或目标符号链接拒绝覆盖。
新建文件权限为 0600，新建目录 0700；这些私人报告不能随开源项目发布。
命令输出 JSON 只含汇总与产物路径，`--validate` 不写入文件。输入错误退出码 2；合法但巡检未完成仍为成功，查看 `complete:false`。

测试：`python3 -m unittest discover -s 00-工作流系统/tests -p test_inbound_digest.py -v`。
