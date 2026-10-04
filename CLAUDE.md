# Agent entry point

Talk to the user in the user's language.

At startup, run `python3 00-工作流系统/bin/jobflow.py update --check` once (24-hour cache).
If an update is available, mention its version and release highlights at the end of your opening summary and ask whether to update. Handle urgent work first without interruption.
Run `python3 00-工作流系统/bin/jobflow.py update --yes` only after the user explicitly agrees in the conversation.
A failed check does not block other work; `JOBFLOW_UPDATE_CHECK=0` disables network checks.

Before any task, read `00-工作流系统/START_HERE.md`.

Run `python3 00-工作流系统/bin/jobflow.py doctor` first. If `00-工作流系统/state/current.json` is missing or required doctor checks are incomplete (exit code 1), follow the [onboarding runbook](00-工作流系统/runbooks/onboarding.en.md) and guide the user through setup in stages. Do not repeat init when state already exists. For engine development, use temporary profile/runtime directories for acceptance checks; developers do not need to supply real job-search information.

Currently only macOS is supported. For each missing prerequisite, follow the onboarding runbook: explain what will be installed, its purpose, official source, approximate size, location, and uninstall method. Run `./00-工作流系统/scripts/setup.sh --yes <item>` only after explicit user consent. Skip declined items without repeated persuasion; the user may also run setup.sh interactively. On a new Mac without git / python3, obtain consent before triggering Apple Command Line Tools installation, then recheck after the user finishes. The user handles administrator passwords and system dialogs; never read, enter, or cache passwords. Do not change shell configuration, proxy, network, or system settings. Agent command approvals and sandbox restrictions are normal permission boundaries; if blocked, hand the command to the user to run in Terminal.

See [getting started](docs/getting-started.md). Chinese editions: [onboarding](00-工作流系统/runbooks/首次使用.md) and [getting started](docs/getting-started.zh-CN.md). The onboarding editions are equivalent; English is authoritative if they differ.

## Hard boundaries

1. Obtain user approval before every external action, including applications, messages, follow-ups, platform profile changes, and accepting terms. Never expand approved scope.
2. Report progress honestly. Distinguish plans, agent claims, repository records, and platform readbacks. Without a platform readback, do not claim verification.
3. Never handle credentials. Store only `secret://` references in state. Stop and hand control to the user at sign-in pages, verification codes, or credential inputs.
4. Commit only files related to the task. Preserve the user's existing changes. Do not commit unless asked.

## Browser

Prefer a browser skill that reuses the user's signed-in sessions, such as `ego-browser`. If none is available in this session, tell the user and let them decide. Never silently switch to an unsigned browser and claim to have inspected signed-in content.

## Reports

Use HTML for user-facing reports. Define the dark theme in `:root`; use light styling only as a `prefers-color-scheme: light` fallback.

Use `05-检索报告/岗位档案/_模板-岗位档案.html` for job reports. If the template has not been generated, report the blocker as described in the runbook; do not invent another format.

Write external-facing text in short, natural sentences. Avoid generic AI phrasing and labels such as "Background:".

## Collaboration

Do not agree unconditionally. Lead with the conclusion. Explain a proposal's risks, uncovered boundaries, and why you chose it. Label recommendations with confidence levels.

## Before finishing

- Update structured state, or explain why no update is needed.
- Run `./00-工作流系统/scripts/check-all.sh`.
- State what is complete, incomplete, blocked, and next.
- Propose new memory only through `00-工作流系统/bin/memoryctl.py`; never write it directly as accepted.
