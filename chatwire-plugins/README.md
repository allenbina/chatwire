# chatwire-plugins

Community plugin registry for [chatwire](https://github.com/allenbina/chatwire).

## plugins.json

This file is fetched by chatwire's plugin marketplace (Settings → Browse Plugins).

### Schema

Each entry:

```json
{
  "name": "chatwire-ntfy",
  "pypi": "chatwire-ntfy",
  "description": "Human-readable description.",
  "author": "github-username",
  "signed": true,
  "homepage": "https://github.com/...",
  "icon": "🔔"
}
```

`signed: true` — package carries a valid chatwire Ed25519 signature (official plugins only).
`signed: false` — community plugin, installed at user's own risk.

## Submitting a plugin

Open a pull request adding your entry to `plugins.json`. Community plugins are reviewed for obvious malware; they are not cryptographically signed by the chatwire project.
