# Discord Bot — AI Ticket Creation

## Goal
Allow contributors and community members to discuss issues in Discord and have Claude
summarize the conversation into a GitHub issue automatically.

## Planned Flow
1. Discussion happens in a designated Discord channel
2. A maintainer runs `/ticket` slash command
3. Bot grabs the last N messages as context
4. Sends to Claude API: "Summarize this discussion into a GitHub issue title and body,
   including a Discussion Summary section covering what was decided and what was ruled out"
5. Claude returns a draft — bot posts it in Discord for confirmation
6. On confirm, bot calls GitHub API to create the issue with appropriate labels

## Privacy
- Bot must scrub PII before sending to Claude API or GitHub
- No real phone numbers, contact names, or message content in issues
- Bot warns if it detects potential PII in the draft

## Stack
- discord.py or discord.js
- Anthropic API (claude-sonnet-4-6)
- GitHub REST API (PyGithub or octokit)
- Can be hosted on existing homelab infrastructure

## Status
Planned — not yet implemented.
