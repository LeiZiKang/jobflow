**English** | [中文](getting-started.zh-CN.md)

# Getting started

Prepare your goals, resume, and preferred job sites. Then let your agent guide you through setup. You do not need every answer in advance.

## The easiest way to start

Currently only macOS is supported. You only need to install the [Claude desktop app](https://claude.ai/download) (Code tab) or [Codex](https://chatgpt.com/codex), then tell your agent:

> Clone https://github.com/LeiZiKang/jobflow locally, then help me initialize it.

The agent can handle cloning too. It checks everything else and asks item by item, explaining what it installs, why, the official source, approximate size, destination, and how to uninstall. If you decline, it skips that item without asking again.
On a new Mac without git / python3, it first obtains consent to trigger `xcode-select --install`. You complete the Apple Command Line Tools dialog, then it continues cloning and setup.
You handle administrator passwords, system dialogs, and platform sign-ins yourself. No shell configuration, proxy, network, or system settings are changed.


## What to prepare

| Item | Requirement |
|---|---|
| System | Currently macOS only; install the agent first, consent to other tools individually |
| Python | 3.9 or later; the engine uses only the standard library |
| Agent | Claude Code, Codex, or another agent that can work in a local repository |
| Node | 20.9 or later, only for the console |
| Browser | ego lite is recommended, with the ego-browser skill enabled in your agent |
| Job sites | Choose your channels and sign in yourself |
| Resume | At least one PDF, Markdown, JSON, DOCX, or TXT file |
| Optional material | Portfolio links, ongoing conversations or applications, identity details |

Use the [ego lite website](https://lite.ego.app/) for installation. With consent, setup.sh installs its official DMG. The browser lets agents reuse your own signed-in sessions. After installing it, make sure your agent has the `ego-browser` skill and the `ego-browser` command is on PATH.

You can set up jobflow without it. Your agent will be limited to public pages in a browser that is not signed in, so much of the content on recruiting platforms may be unavailable. The agent asks before installing software and does not silently switch browsing methods.

Possible channels include BOSS直聘 (BOSS Zhipin), 猎聘 (Liepin), LinkedIn, Indeed, 前程无忧 (51job), and company careers sites or applicant tracking systems (ATS). Sign in only to the sites you intend to use. Handle passwords and verification codes yourself; never give them to the agent. Checking job-related email or Slack messages requires separate agreement on scope.

Place your resume in `03-简历/` (resumes); subfolders are supported. README files do not count. The agent reads the original facts and asks before adapting application materials. Do not add identity documents, passwords, or other secrets.

## Check the environment and install with consent

From the repository root, run `./00-工作流系统/scripts/setup.sh --check`. It reuses doctor without changes; exit 1 means required setup is incomplete. Without working Python it reports that doctor cannot run and other checks are unknown.
Run `./00-工作流系统/scripts/setup.sh` for interactive setup. Each explanation is followed by `[y/N]`; Enter skips.
An agent may use `./00-工作流系统/scripts/setup.sh --yes <item>` **only after explicit user consent for that item in the conversation**. It installs one item, never an implicitly approved bundle.

| item | Source, purpose, destination | Estimated size and removal |
|---|---|---|
| `xcode_clt` | Apple Command Line Tools provide git / python3, not full Xcode; [Apple](https://developer.apple.com/download/all/) system installer; `/Library/Developer/CommandLineTools` | About 1–3 GB download and several GB installed; Apple gives the actual size. User removes the tools directory and handles admin authentication |
| `node` | [Official Node.js](https://nodejs.org/) LTS for arm64 / x64; verify matching `SHASUMS256.txt`; `JOBFLOW_TOOLS_DIR/node` | About 40–70 MB download, 150–250 MB installed; remove that node directory |
| `console_dependencies` | Console packages from the [official npm registry](https://registry.npmjs.org/); `npm ci` when a lockfile exists; `console/node_modules` | About 100–500 MB download, 0.5–1 GB installed; remove node_modules and `JOBFLOW_TOOLS_DIR/npm-cache` |
| `ego_browser` | Official [ego lite](https://lite.ego.app/) DMG → `~/Applications`; skip if the app or command exists | Estimate 200–500 MB download, 0.5–1 GB installed, varies by release; quit and move app to Trash; manage browser data in the app |
| `menubar_app` | Optional; fixed latest asset `Jobflow.dmg` from [GitHub Releases](https://github.com/LeiZiKang/jobflow/releases) → `~/Applications/Jobflow.app` | Estimate 1–30 MB, depends on release; quit and move app to Trash |

`JOBFLOW_TOOLS_DIR` defaults to `~/.local/share/jobflow/tools`. A qualified Node ≥ 20.9 on PATH takes precedence. Otherwise doctor, check-all, and console launchers automatically use the private node. No Homebrew, sudo, or `.zshrc` / `.zprofile` edits.
`JOBFLOW_APPLICATIONS_DIR` overrides the user app destination; `JOBFLOW_SYSTEM_APPLICATIONS_DIR` overrides system app discovery (default `/Applications`). Tests use temporary locations for both.

After installing ego lite, follow its first-run setup and enable the agent-side `ego-browser` skill. Finding an app does not verify the skill or platform sign-ins.
For the Jobflow menu bar app: The DMG is notarized by Apple and opens normally. Right after a release you may briefly get a temporary un-notarized build; if macOS blocks it, right-click → Open, or System Settings → Privacy & Security → Open Anyway. Do not disable Gatekeeper. Select the repository folder on first launch. Developers can still build with `./00-工作流系统/menubar-app/build.sh`.

Claude Code may ask to confirm commands. Codex's default sandbox may block networking or home-directory writes; the user can grant access or run the interactive script in Terminal. These are normal permission steps. The installer only opens system dialogs; passwords are never read, entered, or cached by the agent or script.
Download failures report network, HTTP, or certificate errors and the manual sources above, without repeated retries or proxy changes. Doctor runs after each installation. For Apple's installer, wait until the user confirms completion before checking again. `--check` uses doctor's readiness exit code. Installation mode exit 0 means no execution failure; `pending-user` still awaits the user and does not mean the workspace is ready.
Personal-data checks cannot be installed and have `install: null`; complete them through onboarding.


## What the first conversation covers

Open the repository in your agent and say “Help me set up jobflow.” The [onboarding runbook](../00-工作流系统/runbooks/onboarding.en.md) ([Chinese edition](../00-工作流系统/runbooks/首次使用.md)) tells it to ask only for missing information, usually 2–4 questions at a time. If you give several stages of answers at once, it can summarize them together for one confirmation before writing. Explicit permission for a specific write does not need to be requested again; silence or “skip” is not confirmation:

1. Your system, agent, and missing tools. Would you like a demo or an empty workspace?
2. Target roles and seniority. Which cities, remote arrangements, and commutes work for you?
3. Preferred industries or employer types: foreign-owned, domestic, or either?
4. Minimum and target pay, including currency and pay basis. When could you start?
5. What matters most? Example weights are technical experience 30, working hours 25, growth 20, pay 15, and culture and leave 10. Add or remove factors; the total must be 100.
6. Keep or change the example thresholds: a supported score of 75, evidence coverage of 80, and rejection when even the upper bound is below 50? Prefer verified foreign-owned employers within the same recommendation group? An unanswered `foreign_first` stays null; scoring still works without ownership-based sorting. Scores are not hiring probabilities.
7. Deal-breakers, such as client-site outsourcing, a one-person team, or sustained extreme overtime?
8. Set up ego lite? Which platforms should be used, and which are already signed in?
9. Which resumes, portfolio links, and existing opportunities should be included? Would you like to provide an optional identity.json?
10. Use the console or scheduled tasks?

Unanswered questions stay null or undecided in your personal `onboarding.json`. The current scoring contract requires explicit weights, thresholds, and at least one hard rule. If these are undecided, or you have no hard rules, the agent will explain that scoring is not ready. It must not invent answers to pass validation. `foreign_first` accepts true, false, null, or omission. Only true enables a preference for verified foreign-owned employers within a group. Null or omission means undecided and does not block scoring; the agent must not substitute true or false. Details such as your start date stay in the interview record rather than being forced into the scoring format.

## Start manually and check readiness

Clone the repository and enter it:

Manual route: if git / python3 is unavailable, run `xcode-select --install` in Terminal and complete the Apple dialog yourself.

```bash
git clone https://github.com/LeiZiKang/jobflow.git
cd jobflow
```

From the repository root:

```bash
python3 00-工作流系统/bin/jobflow.py init
python3 00-工作流系统/bin/jobflow.py doctor --lang en
```

`00-工作流系统` is the workflow engine directory. The first init creates state and example goals. Doctor will normally exit with code 1: customized goals, a resume, and confirmed channels are still missing.

Complete the interview with your agent, or edit your personal goals using the structure in `00-工作流系统/examples/screening/goals.example.json`. Formatting changes alone do not count: doctor compares the parsed JSON. Once you have chosen channels, copy the templates to your personal directory and edit the copies:

```bash
PROFILE_DIR="${JOBFLOW_PROFILE_DIR:-$HOME/.config/jobflow/profile}"
mkdir -p "$PROFILE_DIR"
# -i asks before replacing an existing file
cp -i "00-工作流系统/config/search_channels.json" "$PROFILE_DIR/search_channels.json"
# Only if you want inbox checks and have agreed on their scope
cp -i "00-工作流系统/config/inbound_sources.json" "$PROFILE_DIR/inbound_sources.json"
```

Trim `required_daily` / `sources`. Update search terms, location, coverage requirements, and the company list. Fill every template placeholder from the interview, including role keywords, target location or remote work, pay, hard rules, and target companies. Do not carry placeholders into a working configuration. A null daily company count means the coverage requirement has not been agreed yet. Keep personal preferences out of the tracked config templates. Do not create the search_channels override until you have decided. An explicitly agreed empty list is valid if you only want to supply job listings manually.

```bash
python3 00-工作流系统/bin/jobflow_screening.py --validate-profile
python3 00-工作流系统/bin/jobflow.py config search_channels.json
python3 00-工作流系统/bin/jobflow.py doctor --lang en --json
./00-工作流系统/scripts/check-all.sh
```

Doctor has **seven required checks**: macOS, Xcode Command Line Tools, Python, initialized state, valid goals that differ from the example, a resume, and a personal channels override. All must be ok for exit code 0; otherwise it returns 1. Node absence is marked missing; Node, console dependencies, ego-browser, the menu bar app, and identity.json remain optional. Console dependencies pass only when both `console/node_modules/.bin/tsc` and `.bin/next` exist and are executable. An empty or incomplete install produces a warning: rerun `./00-工作流系统/scripts/setup.sh`. Doctor and check-all share this check. Installed dependencies do not prove that the build passes.

Doctor prints no goals or identity content and does not sign in to websites. The config command does print your selected channel configuration; do not paste it into a public issue.

**Ready** means the required doctor checks pass and check-all passes. This does not verify resume facts, platform logins, or channel availability. Start with one manual, read-only job search before scheduling recurring runs.

## Where data lives

| Content | Location |
|---|---|
| Goals, channels, interview notes, optional identity | `JOBFLOW_PROFILE_DIR`, default `~/.config/jobflow/profile/` |
| Personal channel overrides | `search_channels.json` and `inbound_sources.json` in that directory |
| Default channel templates | `00-工作流系统/config/`; used only when no personal override exists |
| Resumes | `03-简历/` |
| Progress, evidence, approvals | `00-工作流系统/state/`, `evidence/`, `approvals/`, etc. |
| Job-search reports | `05-检索报告/` (search reports) |
| Local service runtime data | `JOBFLOW_RUNTIME_DIR`, default `~/.local/state/jobflow` |

The profile directory must be outside the repository. File symlinks must stay inside that directory. Broken overrides cause an error instead of falling back to a template. Directory permissions of 0700 and file permissions of 0600 are recommended. Migrate the profile separately when moving machines, and give scheduled triggers the same environment variables.

User data inside the repository is ignored by Git by default. If you want to version it, change the ignore rules only in a private repository. Never commit it to a public repository.

## Common questions

**Can I try a demo first?**
Run `python3 00-工作流系统/bin/jobflow.py init --demo`. Use `init --force` to reset afterward. Existing core state is backed up to `00-工作流系统/.init-backup-*`. Business files listed in the demo manifest are removed, so do not put real information into demo files. Personal configuration is preserved.

**Why does doctor say my goals are unchanged after init?**
Init copies a neutral template with placeholders. Customize its content and pass profile validation. Whitespace, indentation, and key order do not count as changes.

**Can I start without identity details?**
Yes. identity.json is only needed when preparing application materials. It is not required for search or readiness.

**Can I start without Node or console dependencies?**
Yes, use the CLI. When you want the console, install Node 20.9+, run `./00-工作流系统/scripts/setup.sh`, return to the repository root, and run `./00-工作流系统/local-control/start.sh`. Open `http://127.0.0.1:8788`. Use the launcher instead of `npm run dev` so the local service is connected.

**ego-browser passes, but a platform still asks me to sign in.**
The check only confirms that the command or app exists. Skill availability and active logins must be checked in the current session. You handle sign-in yourself.

**What if check-all fails?**
Confirm that init has completed, then inspect the first error. Share a version of the error without personal data with your agent. Do not fabricate data to pass. Without console dependencies, the TypeScript check is skipped with a warning; install them for full console validation.

**How do I schedule runs?**
The scheduling documents below are currently in Chinese; your agent can help you follow them.
Start with a successful manual run. Then read the [scheduling contract](../00-工作流系统/adapters/SCHEDULED_COMMON.md) and the instructions for [Claude Code](../00-工作流系统/adapters/CLAUDE_CODE_SCHEDULED.md) or [Codex](../00-工作流系统/adapters/CODEX_SCHEDULED.md). External actions still require separate approval.

Updates: ask your Agent to update jobflow, or run `python3 00-工作流系统/bin/jobflow.py update`. See [updates](../README.md#updates) for notifications, privacy and ZIP migration.
