# chatwire-apprise

Multi-service push notifications for chatwire via [Apprise](https://github.com/caronc/apprise).
Supports ntfy, Slack, Discord, Pushover, Gotify, Matrix, PushBullet, and 80+ other services.

## Install

```
pipx inject chatwire chatwire-apprise
```

Then enable via **Settings → Plugins → Apprise** and paste your Apprise URLs
(one per line).

## Apprise URL examples

| Service     | URL format                                     |
|-------------|------------------------------------------------|
| ntfy.sh     | `ntfy://my-topic` or `ntfy://ntfy.sh/my-topic` |
| ntfy (auth) | `ntfy://user:pass@ntfy.sh/my-topic`            |
| Pushover    | `pover://userkey@apptoken`                     |
| Slack       | `slack://TokenA/TokenB/TokenC/#channel`        |
| Discord     | `discord://webhookid/webhooktoken`             |
| Gotify      | `gotify://hostname/token`                      |

Full list: <https://github.com/caronc/apprise/wiki>

## Migrate from chatwire-ntfy

Run the one-time migration helper after installing:

```
python -m chatwire_apprise.migrate
```

This reads your existing `chatwire_ntfy` config and converts it to an
`ntfy://` Apprise URL in `chatwire_apprise.urls`.  Your old config is
preserved; disable or uninstall `chatwire-ntfy` when you're ready.
