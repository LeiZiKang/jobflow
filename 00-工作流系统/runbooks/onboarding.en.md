[中文](首次使用.md) | **English**

The two versions are equivalent. If they differ, the Chinese version takes precedence.
内容对等，以中文版为准。

# First use: an agent-led setup interview

Use this when state is missing or a required `jobflow.py doctor --lang en` check has not passed.
User-facing checklists: [English](../../docs/getting-started.en.md) / [中文](../../docs/新手指南.md).

The stages below are an information checklist, not a questionnaire that must be read out in full. Ask only for missing information, usually 2–4 questions at a time. If the user provides answers for several stages at once, summarize the answers, undecided items, and proposed files together. One confirmation can cover those writes; separate confirmation for every stage is not required.

Do not ask again for explicit permission already given for a specific write, and do not expand its scope. “Skip” or silence is not confirmation. Continue collecting independent information, but leave unconfirmed files unwritten. Read existing files before making local edits, preserving unrelated content. Never invent goals, experience, or preferences. Keep unanswered items null or undecided; examples are not the user's answers. Setup permission covers local preparation, not sign-in, applications, messages, or platform profile changes.

## 0. Environment

Currently only macOS is supported. Start with:

```bash
python3 00-工作流系统/bin/jobflow.py doctor --lang en --json
./00-工作流系统/scripts/setup.sh --check
```

Incomplete readiness is normal on first use. JSON does not print goals or identity content. Software checks have an `install` item name; personal-data checks have null. Python 3.9+ is required; Node 20.9+ is only for the console.
A new Mac may lack working git / python3. Explain that Apple Xcode Command Line Tools (not full Xcode) provide both, obtain consent, then trigger `xcode-select --install`. If the repository is already present, setup.sh also has a Python-free bootstrap. Only open the dialog; the user completes it. Wait for the user to report completion before running doctor again. Without Python, other checks remain unknown.

For each missing item, explain **what, why, official download source, approximate size, destination, and uninstall instructions**, then ask. See the [installation table](../../docs/getting-started.en.md#check-the-environment-and-install-with-consent). Order: `xcode_clt`, `node`, `console_dependencies`, `ego_browser`, optional `menubar_app`. Skip ready items. A refusal means skip without persuasion or implicit dependency installation.

Only after explicit conversational consent for that item may the agent run (node is an example):

```bash
./00-工作流系统/scripts/setup.sh --yes node
python3 00-工作流系统/bin/jobflow.py doctor --lang en
```

Alternatively the user can run `./00-工作流系统/scripts/setup.sh` in Terminal and answer each `[y/N]`. Choosing the console does not silently authorize all software. `--yes` is not a blanket unattended switch.
Claude Code may show command approval. Codex's default sandbox may block networking or home-directory writes; the user must grant access or run the interactive script in Terminal. These are normal permission prompts, not restrictions to bypass.
Only the user handles administrator passwords and system authorization dialogs. Neither agent nor script reads, enters, or caches passwords. Do not modify shell configuration, proxy, network, or system settings. On download failure, report the reason and official manual source without repeated retries or network changes.
Recheck after each installation; an unfinished system dialog is pending-user. Do not ask about declined items again in later stages unless the user changes their decision. Summarize remaining gaps and effects. Do not write personal files at this stage.

## 1. Demo or empty workspace

Ask:

1. Would you like to see a demo first or start with an empty workspace?
2. If state already exists, should we complete the missing setup or back it up and reset it?

After confirmation, run only the chosen command:

```bash
python3 00-工作流系统/bin/jobflow.py init --demo
# Or start with an empty workspace
python3 00-工作流系统/bin/jobflow.py init
```

The demo is fictional. After the user has reviewed it and confirmed a reset:

```bash
python3 00-工作流系统/bin/jobflow.py init --force
```

Existing state, events, evidence, approvals, and the brief are backed up to `00-工作流系统/.init-backup-*`. Business files listed in the demo manifest are removed; do not put real information into demo files. Goals and channel files in the personal directory are preserved. Do not use force when an existing real workspace only needs missing setup information.

## 2. Job-search goals

If needed, split the missing information into two rounds. Skip questions already answered:

1. Which role directions and seniority levels do you want? What job keywords describe them?
2. Which cities, remote arrangements, and commutes are acceptable?
3. Do you prefer particular industries or employer types, such as foreign-owned, domestic, or either?

Then ask:

1. What are your minimum and target pay? Confirm currency, gross or net, monthly or annual pay, and number of salary payments.
2. When could you start? Leave it undecided if necessary.
3. Do you have an application-count target? If not, leave it unset. This means cumulative verified applications, not a default quota.

After summarizing and confirming, save the answers in the personal `onboarding.json`, not in public configuration. This is an interview record, not a scoring input. Suggested fields are `role_direction`, `level`, `locations`, `remote`, `commute`, `industries`, `company_type`, `salary_floor`, `salary_target`, `salary_basis`, and `earliest_start`. Use null for unanswered fields. Add confirmed answers from later stages to this record too.

When no target is set, keep `metrics.diagnostic_sample_target` and `metrics.gap_to_target` null in `00-工作流系统/state/current.json`. Do not substitute 15 or 0. Only after the user confirms a number, set a nonnegative integer target and calculate gap as max(target minus verified count, 0). Then run `python3 00-工作流系统/bin/jobflow.py brief --write` and `python3 00-工作流系统/bin/jobflow.py render-views --write`. The demo target of 15 is fictional.

Resolve the personal directory through `jobflow_profile.profile_directory()`. It defaults to `~/.config/jobflow/profile/`, can be overridden with `JOBFLOW_PROFILE_DIR`, and must be outside the repository. See [PRIVATE_PROFILE.md](../PRIVATE_PROFILE.md) (Chinese).

## 3. Evaluation factors and weights

Start from the structure in `00-工作流系统/examples/screening/goals.example.json`. Show the default factors:

| Factor | Default weight |
|---|---:|
| Technical skills and experience | 30 |
| Working hours and life balance | 25 |
| Growth environment | 20 |
| Pay fit | 15 |
| Culture and leave | 10 |

Ask:

1. Which factors should stay, be removed, or be added? What counts as good, partial, or poor fit for each?
2. How should the weights be distributed? Every weight must be positive and the total must be 100. Remove factors that should not be scored.
3. Keep or change the example thresholds: supported score 75, evidence coverage 80, and rejection when even the upper bound is below 50?
4. Within a recommendation group, should verified foreign-owned employers come first? This optional `foreign_first` stays null if unanswered. Do not substitute true or false, and do not block scoring over this question.

Scores describe fit supported by evidence, not the probability of getting hired. Unknown hard rules or insufficient evidence still produce a needs-verification result. Thresholds must be between 0 and 100; `reject_below` cannot exceed `recommend_at`.

Record confirmed weights, thresholds, rubrics, and sorting preferences. Use confirmed role and pay goals in the rubrics. Fill the template placeholders for role and seniority, pay expectations and basis, and growth environment from the interview. Do not carry placeholders forward or guess answers. Write the complete `goals.json` after confirming hard rules in the next stage.

## 4. Hard rules

Ask:

1. What rules out a job entirely, such as client-site outsourcing, a one-person team, or sustained extreme overtime?
2. Which location, minimum pay, or start-date conditions are hard rules, and which are negotiable?

Restate the concrete conditions. After confirmation, write `hard_rules` and the scoring configuration from the previous stage to `goals.json`. Do not apply template rules automatically. A high score cannot compensate for a failed hard rule; missing evidence cannot count as a pass.

The goals contract supports only `schema_version`, `foreign_first`, `dimensions`, `hard_rules`, and `thresholds`. Do not add fields such as start date. `foreign_first` accepts true, false, null, or omission. Only true enables a preference for verified foreign-owned employers within the same group. False, null, and omission do not add an ownership sorting tier; null and omission retain the meaning “undecided.” Write null when the user does not answer.

Weights and thresholds still require concrete values, and at least one nonempty hard rule is required. If those are undecided, or the user explicitly has no hard rules, keep null or undecided in the interview record. Explain that the current scoring contract cannot express this yet. Do not invent rules or defaults to pass validation or announce readiness. Keep drafts in `onboarding.json`; apart from the supported undecided `foreign_first`, do not treat missing scoring inputs as confirmed configuration.

Fill hard-rule placeholders, including the target city or remote-work constraint, from confirmed answers. Remove rules that do not apply.

```bash
python3 00-工作流系统/bin/jobflow_screening.py --validate-profile
```

## 5. Browser and platforms

Ask:

1. Is [ego lite](https://lite.ego.app/) installed? Would you like to prepare it?
2. Which channels should be used: BOSS直聘 (BOSS Zhipin), 猎聘 (Liepin), LinkedIn, Indeed, 前程无忧 (51job), company careers sites / ATS, or others?
3. Which sites have you signed into yourself, and which will you handle later?
4. Which query groups and how many pages, or what stopping condition, should apply to each channel? Do you need a minimum number of company sites per day?

Recommend ego lite because it reuses the user's own signed-in browser sessions. With consent, setup.sh installs the official DMG. Follow ego lite onboarding and enable the agent-side `ego-browser` skill. Doctor checks for a command on PATH or an installed app; it does not verify the skill or platform logins.

Without it, the agent can only read public pages in a browser that is not signed in, and much platform content may be unavailable. Explain the limits and let the user decide. The user handles all sign-ins, passwords, and verification codes. The agent must not handle or bypass them.

After confirmation, copy `00-工作流系统/config/search_channels.json` to the personal directory and trim `required_daily` to the selected channels. Fill role-keyword, target-city-or-remote, coverage, company-list, and completion placeholders from the interview. Do not reuse template placeholders. A null minimum company count means it has not been agreed; it is not an automatic coverage target.

Channel confirmation does not verify platform access or authorize applications. Do not create the override while channel selection is undecided. If the user explicitly wants to provide jobs manually, an agreed empty list is valid; explain that automatic search will not run.

If inbox checks are needed, ask two more questions: which platform inboxes should be checked, and is job-related email or Slack access authorized? After confirmation, copy `00-工作流系统/config/inbound_sources.json` to the personal directory and trim sources. Search permission does not include inbox permission.

Read effective configuration through the shared entry point rather than reading templates directly:

```bash
python3 00-工作流系统/bin/jobflow.py config search_channels.json
python3 00-工作流系统/bin/jobflow.py config inbound_sources.json
```

Personal overrides take precedence. Templates are used only when no override exists, and fallback does not mean channels were confirmed. Broken files or unsafe links cause an error, not silent fallback. Config output may contain personal preferences; do not paste it into public issues.

## 6. Initial files

Ask:

1. Which resume is the source of truth? Place it in `03-简历/` (resumes); PDF, Markdown, JSON, DOCX, and TXT are supported.
2. Are there portfolio links or supporting materials? These can wait.
3. Are any opportunities already in conversation or applied to? May we verify and register them individually?
4. Would you like to prepare `identity.json` now? It is optional and only needed when preparing application materials.

Read resume facts without changing them. Confirm each existing opportunity's source, time, and actual status before recording it as inbound or an application. File presence does not verify resume content; README files do not count. Summarize the file list and optional items, then update the interview record after confirmation.

## 7. Optional components

Ask:

1. Use the console now, or start with the CLI?
2. Configure scheduled tasks, or begin with a manual run?

After confirming console use:

```bash
./00-工作流系统/scripts/setup.sh  # 逐项同意 / per-item consent
./00-工作流系统/local-control/start.sh
```

Open `http://127.0.0.1:8788`. On macOS, the root launcher can also be opened by double-clicking it. For scheduling, follow `00-工作流系统/adapters/SCHEDULED_COMMON.md` and the relevant `CLAUDE_CODE_SCHEDULED.md` or `CODEX_SCHEDULED.md` in that directory (currently Chinese). External triggers must inherit the same `JOBFLOW_PROFILE_DIR`. Confirm time, timezone, and scope before configuring them. Scheduling does not authorize applications, messages, sign-in, or profile changes.

## 8. Ready

```bash
python3 00-工作流系统/bin/jobflow.py doctor --lang en
./00-工作流系统/scripts/check-all.sh
```

Say “ready” only when every required doctor check is ok (exit code 0) and check-all passes. Missing/warn optional items do not change doctor's exit code, but explain their impact. Console dependencies are ready only when both `.bin/tsc` and `.bin/next` exist and are executable. An empty node_modules or incomplete installation needs setup.sh with per-item consent. Passing the dependency check does not prove that the build passes. Readiness does not mean every platform is accessible or external actions are authorized.

Summarize goals, weights, hard rules, channels, resumes and other files, undecided items, and remaining warnings. Ask:

1. Is this setup summary accurate? Do not repeat confirmation for unchanged information already covered by a combined confirmation.
2. Would you like to run one manual, read-only search using the selected channels now?

Only after confirmation, follow `00-工作流系统/runbooks/每日岗位检索.md` (daily job search, currently Chinese). Do not initialize again. Update structured state or explain why this stage needs no state update. New memory may only be proposed through `memoryctl.py`.
