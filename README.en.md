[中文](README.md) | **English**

# jobflow

A repository-based job-search workflow for AI agents.

Goals, progress, evidence, and approvals each have a defined home. A new agent or session can pick up from the files. Plans, agent claims, repository records, and verified platform results are recorded separately. You approve applications, messages, profile edits, and other external actions before they happen.

## How it works

- The repository holds state, tasks, evidence, and reports. Personal goals and channel settings live outside it.
- One lead agent, the Decider, makes decisions and assigns bounded task envelopes to executing agents.
- Hard rules, scoring weights, and evidence coverage determine recommendations. Scores are not hiring probabilities.
- External schedulers trigger runs; the repository defines their scope.
- A local console shows candidates, applications, reports, and agent runs. The CLI also works on its own.

## Before you start

Read the [getting-started guide](docs/getting-started.en.md). Think about your goals, weights, deal-breakers, and preferred channels.

- macOS or Linux, Git, and Python 3.9+. The engine uses only the standard library.
- Claude Code, Codex, or another agent that can open a local repository.
- At least one resume in `03-简历/` (resumes): PDF, Markdown, JSON, DOCX, or TXT.
- [ego lite](https://lite.ego.app/) and the agent-side `ego-browser` skill are recommended to reuse your signed-in browser sessions. The official installation script currently supports macOS only. Without it, agents can only read public pages in a browser that is not signed in.
- Choose channels such as BOSS直聘 (BOSS Zhipin), 猎聘 (Liepin), LinkedIn, Indeed, 前程无忧 (51job), or company careers sites / ATS. Sign in yourself. The agent never handles your passwords or verification codes.
- Optional: Node 20.9+ for the console; Xcode Command Line Tools for the macOS menu bar app; portfolio links, existing opportunities, and identity.json.

## Quick start

```bash
git clone <repo-url>
cd jobflow
```

Open the repository in your agent and say “Help me set up jobflow.” The [onboarding runbook](00-工作流系统/runbooks/首次使用.md) guides it through 2–4 questions at a time. It repeats your answers back and asks for confirmation before writing files.

You can also start manually:

```bash
python3 00-工作流系统/bin/jobflow.py init
python3 00-工作流系统/bin/jobflow.py doctor
```

`00-工作流系统` means workflow system and contains the engine. Doctor normally returns 1 after the first init: you still need customized goals, a resume, and confirmed channels.

`config/search_channels.json` and `config/inbound_sources.json` under that directory are default templates. After agreeing on scope, copy them to `JOBFLOW_PROFILE_DIR` (default `~/.config/jobflow/profile/`) and edit the copies. Keep personal preferences out of tracked files. See the getting-started guide for steps. Personal overrides take precedence; templates are used only when an override is absent:

```bash
python3 00-工作流系统/bin/jobflow.py config search_channels.json
python3 00-工作流系统/bin/jobflow.py config inbound_sources.json
python3 00-工作流系统/bin/jobflow.py doctor --json
./00-工作流系统/scripts/check-all.sh
```

**Ready** means every required doctor check is ok and check-all passes. Doctor does not print goals or identity content. Missing Node, console dependencies, ego-browser, or identity.json only produces warnings and does not change doctor's exit code. Platform logins and actual access still need verification. Start with one manual, read-only job search.

To explore fictional demo data first:

```bash
python3 00-工作流系统/bin/jobflow.py init --demo
# After reviewing the demo and confirming a reset
python3 00-工作流系统/bin/jobflow.py init --force
```

Reset backs up existing core state to `00-工作流系统/.init-backup-*`. Business files listed in the demo manifest are removed, so do not put real data into demo files. Configuration in the personal directory is preserved.

## Open the console

```bash
cd console && npm install
cd ..
./00-工作流系统/local-control/start.sh
```

Open `http://127.0.0.1:8788`. On macOS, you can also double-click `打开本地求职控制台.command` (open the local job-search console). Use the launcher instead of `npm run dev`; it connects the local service.

For a read-only dashboard without Node: `./打开看板.command` (open dashboard).
For the macOS menu bar app: `./00-工作流系统/menubar-app/build.sh`.

## Daily workflow

| Step | How you and the agent work together | Runbook |
|---|---|---|
| Search | Agree on read-only scope, read job descriptions in selected channels, and save sources | [Daily job search](00-工作流系统/runbooks/每日岗位检索.md) |
| Review | Read fit, risks, and unknowns; decide whether to apply to each specific role | [Job reports](00-工作流系统/runbooks/岗位报告撰写.md), [scoring](00-工作流系统/runbooks/目标评分与推荐.md) |
| Prepare and apply | Check facts, approve exact text and attachments, then give final confirmation | [Applications](00-工作流系统/runbooks/投递.md) |
| Follow up | Read platform status and update evidence; sending requires separate approval | [Follow-up](00-工作流系统/runbooks/跟进.md) |
| Interviews and review | Provide materials, verify facts, and prepare questions and reflections | [Interview preparation](00-工作流系统/runbooks/面试准备.md), [ongoing workflow](00-工作流系统/runbooks/推进求职.md) |

The agent can organize materials, validate data, and create local reports. External actions require approval, and approved scope cannot be expanded silently.

## Scheduled tasks

External schedulers start runs on time. Repository task envelopes still define the work. Complete a manual run before scheduling.

- [Common contract](00-工作流系统/adapters/SCHEDULED_COMMON.md)
- [Claude Code](00-工作流系统/adapters/CLAUDE_CODE_SCHEDULED.md)
- [Codex](00-工作流系统/adapters/CODEX_SCHEDULED.md)

Triggers must use the same `JOBFLOW_PROFILE_DIR`. Search channels and inbox sources come from personal overrides.

## Data and directories

| Path | Purpose |
|---|---|
| `JOBFLOW_PROFILE_DIR` (default `~/.config/jobflow/profile/`) | Goals, personal channel settings, onboarding notes, optional identity |
| `JOBFLOW_RUNTIME_DIR` (default `~/.local/state/jobflow`) | Local service SQLite, token, and pid files |
| `00-工作流系统/` (workflow system) | Engine, protocols, CLI, runbooks, tests, local services |
| `00-工作流系统/state/`, `evidence/`, `approvals/` | State, evidence, and approvals created after initialization |
| `console/` | Local Next.js console |
| `01-现在在做/` (current work) | Active applications, candidates, status views |
| `02-策略/` (strategy) | Personal strategy and reviews |
| `03-简历/` (resumes) | Resume materials |
| `04-面试/` (interviews) | Interview preparation and cases |
| `05-检索报告/` (search reports) | Job reports, catalog, and search results |

The personal directory must be outside the repository. User data inside the repository is ignored by `.gitignore` by default. If you want to version your job-search data, change these rules only in a **private repository**. Never commit it to a public repository.

## Safety boundaries

- The agent does not handle passwords, verification codes, cookies, or tokens. It hands control back at sign-in or verification screens.
- State may contain `secret://` references, never actual secrets.
- Search permission does not authorize applications, messages, accepting terms, or profile edits.
- Follow each platform's rules. Tool availability does not imply permission for every automated action.

## Common questions

**Why am I not ready after init?** Init creates the workspace and copies example goals. Run doctor, customize your goals, add a resume, and confirm channels in your personal directory.

**What if ego-browser or Node is missing?** They are advisory checks. The agent must explain browsing limitations; Node only affects the console. You can also leave identity.json for later.

**What if check-all fails?** Confirm that init has completed, then address the first error. Without console dependencies, the TypeScript check is skipped with a warning.

See the [getting-started guide](docs/getting-started.en.md) for more detail.

## Development

```bash
./00-工作流系统/scripts/install-hooks.sh
```

- `check-all.sh`: validation, generated views, and unit tests. Run init first; fictional demo data is suitable. TypeScript is checked when console dependencies are installed.
- `check-publishable.sh`: checks files to be published and Git history for sensitive content. Keep private keywords outside the repository in `~/.config/jobflow/publish-denylist.txt`, or set `JOBFLOW_PUBLISH_DENYLIST`.
- Tests must use temporary `JOBFLOW_PROFILE_DIR` and `JOBFLOW_RUNTIME_DIR` directories, never real personal configuration.

## License

MIT. See [LICENSE](LICENSE).
