# Tinfoil Hat (E2E Encryption)

## What it does

The Tinfoil Hat plugin adds symmetric end-to-end encryption to your iMessages using AES-256-GCM with per-contact shared passphrases. Encrypted messages are stored in `chat.db` as a `🔒` prefix followed by a base64url-encoded ciphertext blob; the plugin decrypts them transparently in the web UI and in any relay integration. Your contact needs to use the same passphrase (via the same chatwire setup or a compatible implementation) to read the messages.

Keys are derived from passphrases using PBKDF2-SHA256 (100,000 iterations), making brute-force attacks costly. The encryption is symmetric: both parties use the same shared secret — there is no public-key exchange. This is "tinfoil hat" grade security: strong against passive observers and nosy relays, but only as strong as the shared passphrase and the security of how you exchange it.

## Install command

Tinfoil Hat ships with chatwire. No additional install is required. The `cryptography` package (already a chatwire dependency) provides the crypto primitives.

```
# Already available — enable it in Settings → Plugins → Tinfoil Hat
```

## Configuration walkthrough

1. Open chatwire → **Settings** → **Plugins** → **Tinfoil Hat**.
2. Toggle **Enabled** to ON.
3. Add per-contact passphrases in the **Per-contact passphrases** field. The format is `handle: passphrase`, one per line.
4. Optionally enable **Encrypt by default** to automatically encrypt all outbound messages to contacts that have a configured passphrase.
5. Agree on the same passphrase out-of-band with your contact (in person, or via a separate secure channel).

## Usage guide

### Wire format

Encrypted messages look like this on the wire (in `chat.db` and in the Messages app):

```
🔒<base64url data>
```

The base64url payload contains: 12-byte nonce + 16-byte GCM authentication tag + ciphertext.

### Inbound decryption

When a message arrives that starts with `🔒`:
- If the sender's handle has a configured passphrase → attempt decryption.
  - Success: the plaintext is shown in the web UI (and relayed to integrations).
  - Failure (wrong key or corrupted): `[Encrypted message — wrong key or not for you]` is displayed.
- If no passphrase is configured for that handle → the raw `🔒...` token is shown as-is.

### Outbound encryption

Outbound encryption only fires when **all three** conditions are true:
1. `enabled` is `true`.
2. `encrypt_by_default` is `true`.
3. The recipient handle has a passphrase in `per_contact_keys`.

When active, the message is encrypted before the AppleScript send, so the Messages app and `chat.db` store the ciphertext.

To encrypt a single message without enabling `encrypt_by_default`, manually prepend the `🔒` token (not recommended — use `encrypt_by_default` instead).

### Key exchange

There is no automatic key exchange. You must agree on a shared passphrase with your contact through a separate secure channel (e.g., in person, via Signal, or written on a note). Both parties add the same passphrase to their respective `per_contact_keys` configs.

### Limitations

- **Symmetric only**: Both sides need chatwire (or a compatible implementation). The person you're messaging cannot use the standard Messages app to read encrypted messages.
- **No forward secrecy**: The same derived key is used for all messages with a contact. Compromising the passphrase exposes all past messages.
- **Metadata unprotected**: Sender, recipient, timestamp, and attachment presence are visible in `chat.db` even when message content is encrypted.
- **Group chats**: Tinfoil Hat does not support group chats in this release.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. When off, no decryption or encryption happens. |
| `per_contact_keys` | object | `{}` | Map of handle → passphrase. E.g. `{"+15551234567": "my secret"}`. Both parties must use the same passphrase. |
| `encrypt_by_default` | boolean | `false` | Automatically encrypt all outbound messages to contacts with a configured passphrase. |

Config file: `~/.chatwire/config.json` under `integrations.tinfoil`.

```json
{
  "integrations": {
    "tinfoil": {
      "enabled": true,
      "per_contact_keys": {
        "+15551234567": "correct-horse-battery-staple",
        "alice@example.com": "another-long-passphrase"
      },
      "encrypt_by_default": true
    }
  }
}
```

## Troubleshooting / FAQ

**Encrypted messages show `[Encrypted message — wrong key or not for you]`.**
The passphrase in your `per_contact_keys` does not match what was used to encrypt the message. Verify the passphrase with your contact. Passphrases are case-sensitive.

**Messages are being sent in plaintext even with `encrypt_by_default: true`.**
Check that `enabled` is also `true` and that the recipient handle exactly matches a key in `per_contact_keys` (including `+` prefix and country code for phone numbers).

**The Messages app shows garbled `🔒` text.**
Expected — the Messages app has no knowledge of chatwire encryption. The ciphertext is only decrypted inside chatwire's web UI and relay integrations.

**Can I recover messages if I lose my passphrase?**
No. The ciphertext in `chat.db` cannot be decrypted without the passphrase. Keep a secure backup of your passphrases.

**Is this compatible with iMessage's built-in E2E encryption?**
Tinfoil Hat adds an additional application-layer encryption on top of iMessage's existing E2E transport encryption. The two are independent.
