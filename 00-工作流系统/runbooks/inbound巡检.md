# Runbook：每日全渠道主动联系巡检

author: codex · 2026-09-22

任务 job-inbound-sweep 每天北京时间09:00在早间串行任务第一段执行。以有效 inbound_sources 配置为清单，仅检查用户已确认且启用的来源。模板包含BOSS、猎聘、LinkedIn、Indeed、51job可用消息入口、本机Mail全部已配置账户中的求职邮件、已连接Slack中的求职相关DM/提及。官网/ATS邮件由邮箱覆盖；已有申请门户若有独立收件箱另列。不能把能搜岗位当作能读私信。

用 `python3 00-工作流系统/bin/jobflow.py config inbound_sources.json` 读取有效配置。
优先读取 `JOBFLOW_PROFILE_DIR/inbound_sources.json`，没有覆盖才回退到默认模板。
需要调整时先复制 `00-工作流系统/config/inbound_sources.json` 到个人目录再编辑。模板不等于授权，
岗位搜索授权也不包括邮箱、Slack 或平台收件箱；先确认来源与范围。

## 执行与窗口

1. scheduled-bootstrap 检查当日slot，NO-OP不重复；Decider领取自己的租约并同步进度。
2. jobflow.py job-envelope --job job-inbound-sweep 生成信封后派执行代理。浏览器只用ego；Mail用只读AppleScript/JXA或授权邮件连接；Slack用现有只读connector。
3. 每来源使用最后成功观察至现在，并保留24小时重叠；首次至少24小时。失败不得推进成功水位。记录window、时区、实际时间、分页/截断范围，积压分批并保留未完成区间。
4. 邮件先看近期收件元数据，再读招聘/面试/申请相关正文。不读密码、验证码、重置链接等认证消息，不输出凭据。不改变已读状态，不发送、删除、移动或归档。
5. 确认发送方和时间后分类：新主动联系、已投回复、面试安排、自动回执、需人工确认。我方消息、平台推广、纯广告不算新inbound。
6. 按平台消息ID去重；缺ID用来源+发送方+时间+正文指纹。跨渠道疑似相同邀约关联但保留证据。与applications及历史草稿比对，已投回复不新建候选。
7. 每条写联系人/公司、岗位、联系时间、要点、来源、目标偏差、建议回/先问清/不建议及理由。只起草，发送另批。
8. 合并JSON后用 python3 00-工作流系统/bin/inbound_digest.py --input <observation.json> --output-dir 05-检索报告/主动联系日报 生成日期HTML及index.html，工作台“报告”自动收录。
9. record-run写coverage及报告路径；validate/check-all后释放租约。没有新联系也生成日报；未查成明确原因。无实质变化通知保持安静，日报仍更新。

## 证据与建议

App-only消息先完整聊天回读确认气泡发送方，仍不明标待确认，不算招聘方回复或无消息。（曾经把我方自己发的消息误判成招聘方回复。）

每来源需source_id、status、observed_at、evidence_ref及范围/原因；blocked数量为null，不写0。部分成功总计写“已查渠道至少N条，其余未知”。not_supported必须有证据。

新联系人按外置goals与目标评分与推荐.md核实主体、用工、团队及工时；股权未知不打真外企。匿名猎头先问雇主。旧调查标日期，建议标置信度和待问项。

## 停止与边界

- 登录、验证码、系统权限弹窗由用户处理，不读取凭据，不绕过。
- ownership_lost停止浏览器，不换空间；其他独立来源可继续。
- 自动审批拒绝写具体动作与理由，不换工具规避。
- 不发送Slack播报或邮件，不自动回复；在当前Codex任务与工作台交付。

## 输出

- evidence/inbound-sweep-<date>/ 保存观察与合并JSON，属于私人业务数据。
- 05-检索报告/主动联系日报/<date>.html 和 index.html 为每日报告与日期入口。
- state/recurring_jobs.json 由record-run记账，旧.md及汇总.html保留。
- 未来公开版本只能导出引擎和虚构样例；真实联系人、邮件、报告与历史不得进入公开仓库。
