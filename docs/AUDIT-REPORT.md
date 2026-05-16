# Doctor-Passed Task Audit Report

> Phase 26 audit — run 2026-05-11.
> All 787 pytest + 163 Vitest pass at time of audit.

| Phase | Chunk | Doctor Commit | Confidence | Notes |
|-------|-------|---------------|------------|-------|
| 1–8 | 15–18 (CI, secrets docs, mobile preview) | early | HIGH | `.github/workflows/ci.yml` exists with vitest + pytest + playwright jobs; `docs/secrets-setup.md` exists; `mobile-preview.yml` exists |
| 1–8 | 19 (legacy Jinja2 UI removal) | early | HIGH | `web/templates/` contains only `wizard/` — old templates gone |
| 1–8 | 20–22 (React password, login, sign out) | early | HIGH | `PasswordSection.test.tsx` exists; `LoginPage.tsx` uses `POST /api/ui/auth/login`; sign out link at `SettingsPage.tsx:2276` |
| 1–8 | 23–31 (tests, CI, a11y, E2E) | early | HIGH | 13 Vitest test files; 5 Playwright E2E specs (`auth`, `login-flow`, `chat`, `settings`, `a11y`); CI runs on push/PR to main |
| 9 | 2 (shadcn/ui component migration) | ca60525 | HIGH | ComposeBox→Button/Textarea; ConversationList→Avatar/Badge; SettingsPage→Accordion; LoginPage→Input/Button; MessageBubble→Badge (DeliveryBadge); Layout→Sheet |
| 10 | 1 (schemes.css + themes.css) | — | HIGH | `schemes.css` has 24 `data-theme` occurrences, HSL values throughout; `themes.css` exists with structural styles |
| 10 | 2 (component updates — no arbitrary syntax) | — | HIGH | `grep -rn 'bg-\[--color'` returns zero matches across all TSX |
| 11 | 1 (SandboxedContext) | — | HIGH | `integrations/sandbox.py` exists with `SandboxedContext`, `SanitizedEvent`, `OfficialMessage`; `bridge.py` has tier-gated `_fan_out()` at line 640 |
| 11 | 2 (PluginFrame + CSP) | — | HIGH | `web/frontend/src/plugins/PluginFrame.tsx` exists; CSP middleware in `web/main.py:242` |
| 11 | 3 (consent UI — tier badges) | — | HIGH | `TierBadge` component at `SettingsPage.tsx:1851`; `TIER_META` covers core/official/notify/ui |
| 11 | 4–5 (read state) | b7f5140 | HIGH | `read_state.py` with `mark_seen` (line 35); `GET /api/ui/read-state` + `POST /api/ui/read-state` + `POST /api/ui/read-state/all` all exist; unread badge in `ConversationList.tsx:126`; Shift+Escape marks all read at line 174 |
| 11 | 6 (notification depth) | 96027e9 | HIGH | `SanitizedEvent.preview` field at `sandbox.py:61`; `notification_depth` settings UI at `SettingsPage.tsx:1243–1321` |
| 17 | 4–6 (plugin updates, logs, logout icon) | 2524852 | MEDIUM | `version_check.py` exists; `LogsPage.tsx` + `GET /api/ui/logs` exist; sign-out **link** present at `SettingsPage.tsx:2276` but renders as plain text — no logout icon from lucide or any icon library is imported or rendered |
| 19 | 1–3 (plugin management) | — | HIGH | `plugin_state.py` exists; `PluginsPage.tsx` exists; `POST /api/ui/plugins/install` (line 1185) and `POST /api/ui/plugins/uninstall` (line 1232) both exist |
| 20 | 1–2 (fuse logic) | 071fb78 | HIGH | Token-bucket + escalating fuse in `chat_send.py:52+`; `CooldownBanner` in `ComposeBox.tsx:37`; fuse checked in `ChatPage.tsx:244` |
| 20 | 4 (429 blocking) | 47cc529 | HIGH | 429 responses in both `api_v1.py:133,137` and `api_ui.py:201,205,217,221,266,270` |
| 20 | 5 (docs/admin Google Form) | — | HIGH | `docs/admin/` contains `unlock-apps-script.js` and `unlock-setup.md` |

---

## LOW confidence items (need fixing)

*None found.* All code referenced in doctor-passed chunks exists and is complete.

---

## MEDIUM confidence items (need re-verification or minor fix)

### Phase 17 Chunks 4-6 — Logout icon missing

**What exists:** `SettingsPage.tsx:2276` renders:
```tsx
<a href="/logout" className="hover:text-foreground">Sign out</a>
```

**What's missing:** No icon is imported from lucide-react or any other library for the sign-out link. The doctor commit (2524852) was described as adding a "logout icon" but the link has no `<LogOut />` or equivalent icon element.

**Fix required:** Import `LogOut` from `lucide-react` and render it inline with the "Sign out" text.

---

## DEPRECATED items (superseded)

*None identified.* All audited chunks remain active and relevant.

---

## Test results at time of audit

```
pytest:  787 passed, 2 warnings
vitest:  163 passed (13 test files)
```
