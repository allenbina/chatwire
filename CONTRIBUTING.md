# Contributing

Thank you for helping improve chatwire.  This document covers everything you need
to get started, whether you want to fix a small bug or take on a larger feature.

---

> **Visibility rule:** If a design decision, bug root cause, or feature scope was
> discussed outside GitHub (in Claude Code, Discord, or elsewhere), a compacted
> summary of that conversation must be posted to the relevant GitHub Issue or PR
> before the work begins or is merged.  GitHub is the canonical record.  Conversations
> that exist only in Claude Code or Discord are invisible to contributors and the
> public.

> **Privacy rule:** Never include PII (phone numbers, email addresses, contact names,
> real message content) in issues, PRs, commits, or screenshots.  Use fake data
> (e.g. "+15551234567", "Sarah Chen", "test message") in all examples and test cases.
> Scrub screenshots before uploading — blur or crop any real contact info.

---

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [How Issues Work](#how-issues-work)
- [Becoming a Regular Contributor](#becoming-a-regular-contributor)
- [Becoming a Maintainer](#becoming-a-maintainer)
- [Setting Up Locally](#setting-up-locally)
- [Making a Change](#making-a-change)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Label Reference](#label-reference)
- [Style Guide](#style-guide)

---

## Code of Conduct

Be direct, be helpful, assume good intent.  This is a small project; keep communication
constructive and on-topic.

---

## How Issues Work

Issues are the primary task queue for this project.  An AI loop (Claude Code) automatically
picks up issues labeled `ai-ready` and opens a pull request.  You can also fix issues
yourself using the process below.

**Issue lifecycle:**
1. Issue opened (by anyone)
2. Triaged by a maintainer — labeled and confirmed
3. Labeled `ai-ready` (AI picks it up) or assigned to a contributor
4. Branch created, changes made, PR opened with `Closes #N`
5. PR reviewed and merged — issue auto-closes

**If you discussed this issue in Discord or Claude Code:**
Paste a compacted summary of that conversation into the issue body under
"Discussion summary."  This keeps the decision history visible and auditable.

---

## Becoming a Regular Contributor

1. Fork the repo and fix something (see [Making a Change](#making-a-change))
2. Open a clean PR — link the issue, describe the change, include a screenshot if visual
3. After a few good PRs, you may be invited to join as a contributor with Write access

Write access allows you to:
- Push branches directly (no fork needed)
- Apply labels to issues
- Review pull requests
- Participate in the maintainer Discord channel

---

## Becoming a Maintainer

Maintainers have deeper involvement in the project direction.  To be considered:
- You have contributed multiple meaningful PRs
- You are available and responsive
- You understand the project's scope and constraints

Maintainers have GitHub Write access and can approve and merge PRs.  Admin access
(repo settings, billing, Claude integration) remains with the project owner.

Reach out in Discord or open a Discussion if you are interested.

---

## Setting Up Locally

```bash
# Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/chatwire.git
cd chatwire

# Add the upstream remote
git remote add upstream https://github.com/allenbina/chatwire.git

# Install Python dependencies
pip install -e '.[dev]'

# Install frontend dependencies
cd web/frontend && npm ci && cd ../..

# Run tests
python -m pytest tests/ --tb=short -q
cd web/frontend && npm test -- --run && cd ../..
```

---

## Making a Change

```bash
# Always start from a fresh main
git checkout main
git pull upstream main

# Create a branch named after the issue
git checkout -b fix/issue-42-login-crash
# or
git checkout -b feature/issue-17-dark-mode

# Make your changes, then commit
git add .
git commit -m "fix: resolve login crash on empty state (#42)"

# Push to your fork
git push origin fix/issue-42-login-crash

# Open a PR on GitHub — link the issue in the PR body
```

**Branch naming:**
- `fix/issue-N-short-description` for bug fixes
- `feature/issue-N-short-description` for new features
- `docs/short-description` for documentation only

---

## Pull Request Guidelines

- Link the issue: include `Closes #N` in the PR body
- Keep PRs focused — one issue per PR
- Existing tests must pass
- If the issue is labeled `regression`, include a test that would have caught the bug
- If the change is visual, include a before/after screenshot (scrub PII first)
- If design decisions were made outside GitHub, summarize them in the PR body
- Never include real phone numbers, contact names, or message content

---

## Label Reference

| Label | Meaning |
|---|---|
| `ai-ready` | Claude Code will pick this up automatically |
| `ai-in-progress` | Claude is working on it |
| `ai-needs-review` | Claude opened a PR — needs human review |
| `regression` | Has occurred before — test required |
| `visual-bug` | UI rendering issue |
| `good-first-issue` | Well-scoped for new contributors |
| `needs-test` | Fix merged but test is still missing |

---

## Style Guide

### General
- Prefer clarity over cleverness
- Small, focused functions and components
- Descriptive variable names — no single letters except loop counters

### Commits
Follow [Conventional Commits](https://www.conventionalcommits.org/):
- `fix:` bug fixes
- `feat:` new features
- `docs:` documentation only
- `refactor:` no behavior change
- `test:` adding or fixing tests
- `chore:` build, config, tooling

Example: `fix: handle null sender on group threads (#88)`

### Comments
- Comment *why*, not *what*
- If a workaround exists because of a known bug, link the issue

### UI / Visual
- Follow existing component patterns before introducing new ones
- Screenshot any visual change in the PR (scrub PII)
- Do not introduce new dependencies for things achievable with existing libraries
