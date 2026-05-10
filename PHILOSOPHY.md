# Philosophy

> *Texting should be personal, meaningful, and human-driven.*

chatwire is a bridge for **a person, on their own Mac, talking to other people on their phones.** That's the only use case it's designed for, and the design choices reflect it.

## What chatwire is for

- Reading your iMessages from a device that isn't a Mac (your phone via Telegram, your homelab dashboard, your terminal)
- Replying to people you actually know, in conversations that matter to you
- Not having to install another dedicated app on your phone to do this
- Owning the path your messages take — no third-party relay, no Firebase, no telemetry

## What chatwire is *not* for

We've made specific architectural choices to discourage these patterns. They're not all hard-blocked, but the path of least resistance points away from them:

- **Mass-send / broadcast.** chatwire's API is rate-limited and oriented around individual conversations. There is no bulk-send primitive.
- **Drip campaigns / scheduled marketing blasts.** No scheduler is built in. The plugin system makes it possible to add one, but it isn't there by default and won't be added to mainline.
- **Spam bots.** The approve/reject ntfy workflow exists for a reason: when an automated process wants to send a message on your behalf, you should know about it and have the chance to say no. The default "agentic" plugins all route through approval, not auto-send.
- **Third-party customer-comms platforms.** There are excellent tools for that already (Twilio, Sendbird, Customer.io). chatwire is not trying to compete with them, and using it for that misses the point.

## On telemetry

I don't have telemetry because I wrote this app for one user — myself — and then decided to open-source it. The only telemetry I want is people helping me make it better.

That means: no analytics, no crash reporters, no "anonymous usage data," no phone-home. If you want to help, open an issue or a PR on GitHub. That's the telemetry the project needs.

## Why this matters

iMessage is a personal medium. The reason BlueBubbles, AirMessage, and chatwire all exist is that millions of people have personal relationships with iMessage contacts who they want to stay in touch with from non-Apple devices. That's a meaningful problem worth solving for.

The same plumbing, pointed at the wrong use case, becomes a vehicle for the kind of unwanted automated text traffic that's eroding texting as a medium. Apple closes loopholes when that happens. The whole bridge ecosystem (BlueBubbles, AirMessage, chatwire) becomes harder to maintain.

So: the policy here is human-in-the-loop by default. Build a plugin that automates something? Great — route it through ntfy approval, set sensible rate limits, and ship it. The architecture supports it. Build a plugin that bulk-blasts your contact list? You can fork chatwire and do that on your own infrastructure, but I won't merge it, the project Discord is not the place to ask for help with it, and the README's positioning is not on your side.

## Things I'm okay with

For clarity, since "no automation" is too narrow:

- **Sending from non-Siri sources.** The whole point of the Mac/web/Telegram/MCP integrations is that Siri is not the only way to send a message. Sending from CLI, from a script, from Claude via MCP, from a Telegram client — all great, all human-initiated.
- **Notifications and routing.** Auto-routing inbound messages to ntfy / Pushover / a webhook is fine. Reading and notifying are different from sending.
- **Scheduled reminders and personal automations.** "Text my partner the grocery list every Saturday at 10am" is a personal automation that the recipient understands and consents to. Plugins can do this. Just don't dress it up as a SaaS marketing channel.
- **Bots in selective, consent-based group chats.** A homelab chat group where a Home Assistant alert occasionally fires is fine. A 50-person chat being auto-summarized by a bot for a stranger's product is not.

The line is: **the recipients of any message chatwire sends should understand and welcome that automation, or there shouldn't be automation at all.**
