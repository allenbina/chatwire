# Chatwire Unlock Code — Admin Setup Guide

This guide walks through creating the Google Form + Apps Script that lets you
approve or deny permanent lockout requests and issue one-time unlock codes.

## Overview

When a user hits anti-spam step 6 (permanent lockout), Chatwire shows them a
machine-bound code (`CW-XXXX-YYYY`) and a link to this unlock form.

1. User submits the form with their machine code and an explanation.
2. Admin reviews the Sheet and sets the Approval column to **Approved** or **Denied**.
3. The Apps Script computes `HMAC-SHA256(cw_code, HMAC_SECRET)` and emails the
   user a one-time `UL-XXXX-XXXX` code.
4. The user pastes the code into the Chatwire lockout overlay → fuse resets.

---

## Step 1 — Create the Google Form

1. Go to [Google Forms](https://forms.google.com) → **Blank form**.
2. Title: **Chatwire Unlock Request**.
3. Add the following questions (all short answer unless noted):

   | # | Question | Type | Required |
   |---|----------|------|----------|
   | 1 | Email address | Short answer | Yes |
   | 2 | Machine code (shown on the lock screen, format: `CW-XXXX-YYYY`) | Short answer | Yes |
   | 3 | What happened? (Brief explanation) | Paragraph | Yes |

4. Under **Settings → Responses**, enable **Collect email addresses** → **Responder input**
   (this populates column B automatically).
5. Click **Send** to get the form URL — copy it; this is your `unlock_form_url`.

---

## Step 2 — Link the Form to a Sheet

1. In the Form editor, click **Responses** tab → **Link to Sheets** (green icon).
2. Choose **Create a new spreadsheet** → name it **Chatwire Unlock Requests**.
3. Open the Sheet. The first row will have headers from the form.
4. Add two more header columns manually:

   | Column | Header |
   |--------|--------|
   | E | Approval |
   | F | Unlock code |

   Your final header row should be:
   `Timestamp | Email address | Machine code | What happened? | Approval | Unlock code`

5. Freeze the header row (**View → Freeze → 1 row**).

---

## Step 3 — Open the Apps Script Editor

1. In the Sheet, go to **Extensions → Apps Script**.
2. Delete everything in the default `Code.gs` file.
3. Paste the entire contents of `docs/admin/unlock-apps-script.js` into the editor.
4. Click **Save** (floppy disk icon).

---

## Step 4 — Set Script Properties

1. In the Apps Script editor, click **Project Settings** (gear icon, left sidebar).
2. Scroll to **Script Properties** → **Add script property**.
3. Add:

   | Property | Value |
   |----------|-------|
   | `HMAC_SECRET` | *(see below)* |
   | `REPLY_FROM` | `chatwireapp@gmail.com` |

### Finding HMAC_SECRET

The `HMAC_SECRET` must match the `unlock_secret` stored in `~/.chatwire/config.json`
on the machine running Chatwire.

```bash
# On the Chatwire host (e.g., mbair):
python3 -c "import config; c = config.load_config(); print(c.get('unlock_secret', 'NOT SET'))"
```

If it prints `NOT SET`, start Chatwire once — it auto-generates and saves the secret on
first use.

> **Important**: Keep this value secret. Anyone with it can generate valid unlock codes.
> Treat it like a private key.

---

## Step 5 — Configure Triggers

1. In the Apps Script editor, click **Triggers** (clock icon, left sidebar).
2. Click **Add Trigger** and set up two triggers:

   **Trigger 1 — Form submit:**
   - Choose function: `onFormSubmit`
   - Event source: `From spreadsheet`
   - Event type: `On form submit`

   **Trigger 2 — Edit:**
   - Choose function: `onEdit`
   - Event source: `From spreadsheet`
   - Event type: `On edit`

3. Grant the requested permissions (Gmail + Spreadsheet).

---

## Step 6 — Wire the Form URL into Chatwire

The "Request unlock →" button in the Chatwire lockout overlay points to this form.
Set the URL via config or environment variable:

**Option A — config.json** (recommended for self-hosters):
```json
{
  "unlock_form_url": "https://forms.gle/your-form-id-here"
}
```

**Option B — environment variable**:
```bash
export CHATWIRE_UNLOCK_FORM_URL="https://forms.gle/your-form-id-here"
```

Restart Chatwire after changing either. The overlay picks up the URL from the
`GET /api/ui/fuse-status` response.

---

## Step 7 — Share the Sheet with Moderators

1. In the Sheet, click **Share**.
2. Add any co-moderators as **Editor**.
3. They can set the Approval column without touching the Apps Script.

---

## Step 8 — Test the Flow

1. In the Apps Script editor, run `testHmac()` manually (select it in the dropdown
   and click **Run**).
2. Copy the expected Python output and verify locally:
   ```bash
   python3 -c "
   import hmac, hashlib
   secret = 'YOUR_HMAC_SECRET_HERE'
   cw_code = 'CW-ABCD-1234'
   digest = hmac.new(secret.encode(), cw_code.encode(), hashlib.sha256).hexdigest()
   print('UL-' + digest[:4].upper() + '-' + digest[4:8].upper())
   "
   ```
3. Both outputs should match.
4. Submit a test form entry, set Approval to **Approved**, verify the email arrives
   and the unlock code matches what the Python snippet above produces.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No email sent on approval | Check that `REPLY_FROM` Script Property is set and the Apps Script has Gmail permission |
| "HMAC_SECRET Script Property is not set" error | Add the property in Project Settings → Script Properties |
| Unlock code is valid but Chatwire rejects it | `HMAC_SECRET` in the Sheet doesn't match `unlock_secret` in config.json |
| Form submissions appear but script doesn't fire | Check Triggers — make sure both triggers are active |
| "Invalid code" after entering UL code | Ensure you're copying the code exactly, including the `UL-` prefix and dashes |
