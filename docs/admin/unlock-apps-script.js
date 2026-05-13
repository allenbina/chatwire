/**
 * Chatwire Unlock Code — Google Apps Script
 *
 * Paste this entire file into the Script Editor for the Google Sheet that
 * is linked to your Chatwire unlock request Form.
 *
 * Set up Script Properties before running:
 *   HMAC_SECRET   — the unlock_secret value from ~/.chatwire/config.json
 *   REPLY_FROM    — email to send from, e.g. chatwireapp@gmail.com
 *
 * Set up two project triggers (Triggers → Add Trigger):
 *   1.  onFormSubmit  — From spreadsheet → On form submit
 *   2.  onEdit        — From spreadsheet → On edit
 *
 * Expected Sheet columns (A-F):
 *   A  Timestamp
 *   B  Email address
 *   C  Machine code (CW-XXXX-YYYY)
 *   D  Explanation
 *   E  Approval        ← admin fills in "Approved" or "Denied"
 *   F  Unlock code     ← script fills in auto-generated UL-XXXX-XXXX
 */

// ---------------------------------------------------------------------------
// Trigger: fires when the linked Form is submitted
// ---------------------------------------------------------------------------

function onFormSubmit(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var row = e.range.getRow();
    var email = sheet.getRange(row, 2).getValue();
    var machineCode = sheet.getRange(row, 3).getValue();

    // Log submission for audit trail
    console.log(
      'Unlock request received — row ' + row +
      ', email: ' + email +
      ', machine code: ' + machineCode
    );

    // Count prior submissions from this machine prefix (first 7 chars: "CW-XXXX")
    var prefix = String(machineCode).slice(0, 7).toUpperCase();
    var lastRow = sheet.getLastRow();
    var priorCount = 0;
    for (var r = 2; r <= lastRow; r++) {
      if (r === row) continue;
      var code = String(sheet.getRange(r, 3).getValue()).slice(0, 7).toUpperCase();
      if (code === prefix) {
        priorCount++;
      }
    }

    if (priorCount > 0) {
      console.log(
        'Note: ' + priorCount + ' prior submission(s) from machine prefix ' + prefix
      );
    }

    // Leave a note in the row if this is a repeat offender
    if (priorCount >= 2) {
      var note = sheet.getRange(row, 4).getNote();
      sheet.getRange(row, 4).setNote(
        (note ? note + '\n' : '') +
        '[AUTO] ' + priorCount + ' prior submissions from this machine.'
      );
    }
  } catch (err) {
    console.error('onFormSubmit error: ' + err);
  }
}

// ---------------------------------------------------------------------------
// Trigger: fires when any cell is edited
// ---------------------------------------------------------------------------

function onEdit(e) {
  try {
    var sheet = e.source.getActiveSheet();
    var range = e.range;

    // Only act on column E (Approval, 1-indexed = 5)
    if (range.getColumn() !== 5) return;
    // Skip header row
    if (range.getRow() < 2) return;

    var approval = String(range.getValue()).trim().toLowerCase();
    if (approval !== 'approved' && approval !== 'denied') return;

    var row = range.getRow();
    var email = sheet.getRange(row, 2).getValue();
    var machineCode = String(sheet.getRange(row, 3).getValue()).trim().toUpperCase();

    // Prevent double-processing: if column F already has a value, skip
    var existingCode = sheet.getRange(row, 6).getValue();
    if (existingCode) {
      console.log('Row ' + row + ' already processed — skipping.');
      return;
    }

    if (approval === 'approved') {
      var props = PropertiesService.getScriptProperties();
      var secret = props.getProperty('HMAC_SECRET');
      if (!secret) {
        throw new Error('HMAC_SECRET Script Property is not set.');
      }

      var unlockCode = computeHmac(machineCode, secret);

      // Write generated code to column F
      sheet.getRange(row, 6).setValue(unlockCode);

      // Send approval email
      sendApprovalEmail(email, machineCode, unlockCode);
      console.log('Approved row ' + row + ' — sent unlock code to ' + email);
    } else {
      // Mark column F so we don't process again
      sheet.getRange(row, 6).setValue('DENIED');

      // Send denial email
      sendDenialEmail(email, machineCode);
      console.log('Denied row ' + row + ' — sent denial to ' + email);
    }
  } catch (err) {
    console.error('onEdit error: ' + err);
    // Re-throw so the error appears in the Apps Script execution log
    throw err;
  }
}

// ---------------------------------------------------------------------------
// HMAC-SHA256 computation — matches chat_send.py _compute_unlock_response()
//
// Algorithm:
//   digest = HMAC-SHA256(key=secret_utf8, message=cw_code_utf8)
//   unlock = "UL-" + hex(digest)[0:4].upper() + "-" + hex(digest)[4:8].upper()
//
// The Python side uses hmac.new(secret.encode(), cw_code.encode(), sha256).hexdigest()
// which means the HMAC key is the raw hex-string bytes (NOT the decoded 32-byte key).
// ---------------------------------------------------------------------------

function computeHmac(cwCode, secret) {
  var rawDigest = Utilities.computeHmacSha256Signature(cwCode, secret);
  var hex = rawDigest
    .map(function(b) { return ('0' + (b & 0xff).toString(16)).slice(-2); })
    .join('');
  return 'UL-' + hex.slice(0, 4).toUpperCase() + '-' + hex.slice(4, 8).toUpperCase();
}

// ---------------------------------------------------------------------------
// Email templates
// ---------------------------------------------------------------------------

function sendApprovalEmail(toEmail, machineCode, unlockCode) {
  var props = PropertiesService.getScriptProperties();
  var replyFrom = props.getProperty('REPLY_FROM') || 'chatwireapp@gmail.com';

  var subject = 'Your Chatwire unlock code';
  var body = [
    'Hi,',
    '',
    'Your request to unlock Chatwire has been approved.',
    '',
    'Machine code:  ' + machineCode,
    'Unlock code:   ' + unlockCode,
    '',
    'To unlock:',
    '  1. Open the Chatwire web UI.',
    '  2. Paste the unlock code above into the "Paste your unlock code" field.',
    '  3. Click Unlock.',
    '',
    'If you did not request this unlock, please ignore this email.',
    '',
    '— Chatwire',
  ].join('\n');

  GmailApp.sendEmail(toEmail, subject, body, { replyTo: replyFrom, name: 'Chatwire' });
}

function sendDenialEmail(toEmail, machineCode) {
  var props = PropertiesService.getScriptProperties();
  var replyFrom = props.getProperty('REPLY_FROM') || 'chatwireapp@gmail.com';

  var subject = 'Chatwire unlock request — not approved';
  var body = [
    'Hi,',
    '',
    'We reviewed your Chatwire unlock request for machine ' + machineCode + '.',
    '',
    'Unfortunately, we were not able to approve this request at this time.',
    'Chatwire is designed for personal, one-to-one communication, not bulk',
    'or automated messaging.',
    '',
    'If you believe this is an error, reply to this email and we\'ll take',
    'another look.',
    '',
    '— Chatwire',
  ].join('\n');

  GmailApp.sendEmail(toEmail, subject, body, { replyTo: replyFrom, name: 'Chatwire' });
}

// ---------------------------------------------------------------------------
// Utility — run manually in the Script Editor to test your HMAC setup
// ---------------------------------------------------------------------------

function testHmac() {
  var props = PropertiesService.getScriptProperties();
  var secret = props.getProperty('HMAC_SECRET');
  var testCode = 'CW-ABCD-1234';
  var result = computeHmac(testCode, secret);
  console.log('computeHmac(' + testCode + ') = ' + result);
  console.log('Paste this into Python to verify:');
  console.log('  import hmac, hashlib');
  console.log('  secret = "' + secret + '"');
  console.log('  cw_code = "' + testCode + '"');
  console.log('  digest = hmac.new(secret.encode(), cw_code.encode(), hashlib.sha256).hexdigest()');
  console.log('  print("UL-" + digest[:4].upper() + "-" + digest[4:8].upper())');
}
