# Chatwire — Messaging & Positioning Ideas

> Raw ideas for press releases, website copy, and brand positioning.
> Not polished copy — themes and angles to pull from.

---

## The One-Liner

**"Your messages, your server, your rules."**

or

**"iMessage, everywhere — without asking Apple's permission."**

or

**"The open-source bridge Apple won't build."**

---

## Core Positioning: What We Are

Chatwire is a self-hosted messaging bridge that runs on your Mac and
gives you access to your own iMessage conversations from any device,
any browser, any platform. It's the app Apple could ship tomorrow but
never will — because keeping iMessage locked to Apple hardware is a
feature, not a bug, for their business model.

We didn't hack anything. We didn't reverse-engineer a protocol. We
read your own database, on your own computer, with your own
permission. That's it.

---

## The Values — What We Chose and What We Didn't

### 1. "Bridges to open platforms"

We connect to Telegram (open API), Matrix (open protocol), and XMPP
(open standard). We don't connect to WhatsApp, Facebook Messenger,
or any platform that prohibits third-party access in their Terms of
Service.

This isn't a technical limitation — it's a choice. We're not
interested in building something that exists in a legal gray area.
If a platform doesn't want third-party clients, we respect that.
The platforms we bridge are the ones that believe in openness.

### 2. "No scheduled messages, no automation, no bots pretending to be you"

Every message sent through chatwire is triggered by a human being.
We don't offer message scheduling. We don't offer auto-replies. We
don't offer "AI that texts for you."

Texting is personal. It should be meaningful, purposeful, and human.
If you're not present enough to send a message yourself, maybe the
message doesn't need to be sent.

### 3. "Zero telemetry. Not 'anonymized telemetry.' Zero."

Chatwire doesn't phone home. No analytics. No crash reporting. No
"anonymous usage data." Your messages stay on your Mac. Your reading
habits stay on your Mac. We don't know how many users we have, and
we're fine with that.

If you want to help us improve, open an issue on GitHub. That's the
telemetry we need.

### 4. "Plugins are a choice, not a mandate"

Chatwire ships with a plugin system and a handful of built-in
integrations. But every plugin is optional. The core app — reading
and sending your messages — works with zero plugins installed.

We built the plugin system so *you* can extend chatwire the way you
want. Not so we can upsell you. Not so we can build a marketplace
that takes a cut. Not so we can inject ads into your conversations.

The plugin SDK is open. The signing system verifies authenticity.
Community plugins are welcome. But the core app will never depend on
one.

### 5. "Self-hosted means self-owned"

Your chatwire instance runs on your Mac. Your messages never touch
our servers — because we don't have servers. There's no cloud
component. There's no account to create. There's no subscription.

`pipx install chatwire` and you're done.

This matters because messaging is the most intimate data most people
have on their devices. Who you talk to, when, how often, what you
say — this is your life in text form. We think you should own it.

---

## The Competition — What They Get Wrong

### BlueBubbles
Requires a Windows or Mac server running .NET, a complex multi-step
setup process, a Firebase project for push notifications, and Google
Cloud credentials. It works, but it's built for tinkerers who enjoy
the setup as much as the result.

Chatwire: `pipx install chatwire`. One command. Done.

### AirMessage
Hasn't been updated since 2023. The UI looks like it was designed in
2018. No plugin system, no theming, no web standards, no accessibility.
A proof of concept that proved the concept and stopped.

Chatwire: 23 themes, WCAG accessibility, plugin SDK, React UI, PWA,
active development.

### Beeper (now Texts.com)
Commercial, closed-source, $10/month subscription. Your messages
route through their servers. They got acquired. They pivoted. They'll
pivot again.

Chatwire: open-source, free, self-hosted, no servers, no subscription,
no acquisition risk. If we disappear tomorrow, your instance keeps
running.

### Pypush / Validation Relay
Clever reverse-engineering of Apple's push notification protocol.
Also the kind of thing that makes Apple's legal team write letters.
Registration-only, no web UI, experimental.

Chatwire: reads your own chat.db with Full Disk Access permission
you explicitly grant. No protocol reverse-engineering. No Apple TOS
gray area.

### Apple (iMessage in iCloud)
Apple could build "iMessage for web" tomorrow. They have the
infrastructure, the protocol, the user base. They won't, because
iMessage lock-in sells iPhones. The green bubble / blue bubble divide
is a feature Apple profits from.

Chatwire exists because Apple made a business decision to keep your
messages hostage to their hardware ecosystem. We just gave you the key.

---

## The Story Nobody Else Has

### "Built by AI, guided by a human"

Chatwire's React migration — 8 phases, 48 commits, full plugin SDK,
mobile app scaffold, CI/CD pipeline, Docker image — was built in a
single afternoon by an autonomous AI development loop. The developer
approved each phase from his phone while running errands.

This isn't a gimmick. It's a proof of what's possible when you
combine clear architectural decisions with autonomous AI execution.
The human set the direction, made the judgment calls, and rejected
the ideas that didn't align with the project's values (no message
scheduling, no WhatsApp bridge, no telemetry). The AI wrote the code.

The entire development history is public. Every commit, every
decision, every "no" — it's all in the repo.

### "From proof of concept to production in 6 waves"

Chatwire started as a personal tool — a way for one developer to
read his iMessages from a Windows laptop. It wasn't designed to be
a product. It was designed to solve a problem.

Six development waves later, it has 23 themes, E2E encryption,
a plugin marketplace, a mobile app, accessibility support, and a
one-command install. Each wave was built by an AI agent, reviewed by
a human, and shipped to a real Mac serving real messages.

The proof-of-concept phase is over. This is the real thing.

---

## Taglines / Pull Quotes

- "Your messages, your server, your rules."
- "The bridge Apple won't build."
- "Zero telemetry. Not anonymized. Zero."
- "Every message is human-triggered. That's the point."
- "One command to install. Zero servers to manage."
- "iMessage on Android, without the gray area."
- "Open bridges to open platforms."
- "We don't know how many users we have. We're fine with that."
- "Built by AI, guided by human judgment."
- "Beeper charges $10/month. We charge nothing, forever."
- "If we disappear tomorrow, your instance keeps running."
- "Texting should be personal. We built chatwire to keep it that way."

---

## Website Sections (suggested)

1. **Hero**: One-liner + screenshot + `pipx install chatwire`
2. **Why**: The Apple problem (iMessage lock-in) in 3 sentences
3. **How it works**: Mac runs bridge → any device connects → your data stays home
4. **Values**: The 5 choices above, each with a one-liner
5. **vs. Competition**: Table comparing chatwire / BlueBubbles / AirMessage / Beeper
6. **Plugins**: Built-in list + "build your own" CTA
7. **Themes**: Grid of all 23 themes (screenshots)
8. **The story**: How it was built (AI loop, human judgment, open development)
9. **Install**: Three paths (pipx, Homebrew, DMG) with copy-paste commands
10. **GitHub**: Star count, last commit, contributor CTA
