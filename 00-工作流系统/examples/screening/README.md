# Evidence-bounded screening (v1)

author: codex

这里所有公司、身份、薪资目标和证据都是虚构示例。不要把示例推荐用于真实求职。

## 运行

```sh
python3 00-工作流系统/bin/jobflow_screening.py \
  00-工作流系统/examples/screening/assessment.example.json \
  --goals 00-工作流系统/examples/screening/goals.example.json
```

真实配置：把自己的 `goals.json`、`identity.json` 分开存于仓库之外的
`~/.config/jobflow/profile/`，或用 `JOBFLOW_PROFILE_DIR` 指定绝对目录。
省略 `--goals` 时只读取外置 `goals.json`，不会打开 `identity.json`。
外置目录及文件经过符号链接解析后仍须位于仓库外，文件不能跳出该目录。
代码不会创建、复制或迁移任何个人资料。建议用户为私人目录设置 0700、文件设置 0600。
`--goals` 是显式输入模式，用于虚构示例和测试；它不会保证指定文件本身位于仓库外。

Python API：`score_assessment(assessment, goals, *, now=None) -> dict`。
`now` 仅供测试注入带时区 datetime；正常运行取 UTC 当前时间。
结果只包含候选 ID、分数、规则解释及证据引用，不输出目标配置或身份对象。
解释来自输入，调用者也应避免把个人身份信息写进 assessment.reason 或 candidate_id。
CLI 成功返回 0，输入错误返回 2；结果写 stdout，错误写 stderr，没有状态写入。

只验证外置目标配置：`python3 00-工作流系统/bin/jobflow_screening.py --validate-profile`。
它不读取 assessment 或 identity，只输出有效状态、维度 ID/权重、硬线数量、排序开关、
policy_version 和 goal_config_sha256，不打印目标正文、rubric、label 或身份。
同样支持 `--goals` 显式配置。评分仍必须提供 assessment 参数。
评分结果也包含这两个版本字段：policy_version 标识算法版本，goal_config_sha256 为
完整已验证目标 JSON 的 SHA-256（UTF-8、ensure_ascii=false、sort_keys=true、紧凑分隔符、
禁止 NaN）。字段顺序与排版不影响 hash，配置内容变化会改变 hash；int 与 float 的
JSON 表示不同也会改变 hash。这不是完整配置备份，复现仍需私人保存对应目标版本。

## 评分与排序

- 维度及权重来自 goals，权重必须合计 100。rubric 明确 0、0.5、1 的含义。
- reviewer 对事实打 0..1，并提供 `evidence_refs`。`null` 或没有证据一律未知。
  引用必须能在 evidence 字典中解析，包含来源、带时区的观察时间和证据摘要。
  observed_at 必须是真实观察时间，不得填未来排期；超过当前时间 5 分钟会拒绝输入。
- `score_lower = Σ(有证据的维度权重 × value)`。
  `score_upper = score_lower + 未知维度权重`。未知不会被删除后重新归一化。
- `evidence_coverage_percent` 是已支持的维度权重比例，不是可信度或录用概率。
- 每条硬线的状态是 pass/fail/unknown。缺少规则或无来源判断会变成 unknown。
  一条有证据的 fail 就整体不推荐，高薪不能补偿。unknown 不会推荐。
- 上限低于 reject_below → 不推荐；否则硬线未知、覆盖不足或最低分未达到
  recommend_at → 待核实；其余推荐。上下限、覆盖率都为 0..100。
- `sort_key` 可按 Python 默认升序排序。推荐 → 待核实 → 不推荐分组；组内若
  foreign_first=true，已核实真外企优先，再比最低分、覆盖率、候选 ID。
  外企优先不越过硬线及证据门槛。上限不用于抢占前排。

## 真外企与用工

`ownership.status=verified_foreign` 必须由研究者核实：这确为外资母公司在华实体，
不能拿境外注册壳、海外上市或少数外资投资替代。程序要求本次已核实的招聘或用工法律主体、最终母公司、
母公司辖区和逐层连续且无环的控制链，每条边都有 control_basis 和来源，才显示「真外企」。
share_percent 可记录股权比例；协议控制、分散股权等由 control_basis 说明，不凭百分比猜控制。
匿名客户、仅招聘品牌、缺任一层证据一律「所有制待核实」。

employment 独立标注「自研产品／外包·交付／用工未核实」。外资交付公司可以同时有
「真外企」和「外包·交付」，这不证明客户团队工时正常。客户是外企也不能给内资雇主
贴「真外企」：ownership 的 legal_entity 必须是本次已核实的招聘或用工法律主体，
不能用猎头客户品牌代替。该标签只描述已核实主体的所有制，不要求等到签劳动合同才赋予；
如果尚未确认实际签约主体，报告必须另行明确写「合同主体待核实」，不得把招聘主体
自动当作最终签约主体。招聘法律主体也无法核实时仍用 unknown。

## 限制与集成

两个 `.schema.json` 是 Draft 2020-12 结构契约，零依赖运行时另做跨字段校验。
程序不访问网站，不验证证据真假、不检查过期、不自动解析 JD 或评估母公司来源地。
这些判断仍须 reviewer 完成；矛盾、过期或弱证据应标 unknown，并解释原因。
JD 没写加班、没有搜到投诉，都不能当作工时硬线已通过的证据。
同一来源可支持多维度，但不代表多个独立信源；权重和阈值需由用户目标校准。

这是独立评分模块，还未自动挂入 collector、HTML renderer 或 scheduler。
它不发送通知或投递，不代表外部行动批准。
外置新配置并不清除现有仓库、报告、state 和 Git 历史中的个人信息；公开前仍需另建
干净引擎仓库、虚构数据及独立隐私检查。
