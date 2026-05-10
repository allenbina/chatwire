# chatwire Mobile — Build & Distribution Guide

> This document covers building and distributing the chatwire Expo app
> for iOS (TestFlight) and Android (APK / Play Store).

## Prerequisites

- Node.js 22+ (`nvm use 22`)
- Expo CLI: `npm install -g expo-cli`
- EAS CLI: `npm install -g eas-cli`
- Logged into Expo: `eas login`
- For iOS: Apple Developer account ($99/year), Xcode 15+
- For Android: Google Play Console account (one-time $25 registration)

---

## 1. Local development

```bash
cd packages/mobile
npm install
npx expo start        # Opens Expo Go on device / simulator
npx expo start --ios  # iOS simulator (macOS only)
npx expo start --android
```

---

## 2. Preview build — iOS Simulator

Builds a `.app` bundle that runs in the iOS Simulator (no Apple Developer
account required for this profile).

```bash
cd packages/mobile
eas build --platform ios --profile preview
```

The build runs on Expo's cloud build infrastructure. Download the `.app`
from the EAS dashboard and drag it into the Simulator.

---

## 3. Preview build — Android APK

```bash
cd packages/mobile
eas build --platform android --profile preview
```

Downloads an `.apk` file. Install on device:

```bash
adb install chatwire-preview.apk
```

Or side-load on Android: enable "Install from unknown sources", transfer
the APK, open it.

---

## 4. TestFlight distribution (iOS production)

> Requires an Apple Developer account and a provisioning profile.

### One-time setup

1. Create an App ID at developer.apple.com → Identifiers:
   - Bundle ID: `dev.chatwire.app`
2. Create an App in App Store Connect (appstoreconnect.apple.com):
   - Name: chatwire
   - Bundle ID: `dev.chatwire.app`
3. Store the App Store Connect App ID in `eas.json` → `submit.production.ios.ascAppId`.
4. Add your Apple ID and Team ID to `eas.json` → `submit.production.ios`.

### Build + submit

```bash
cd packages/mobile

# Build a production iOS IPA
eas build --platform ios --profile production

# Submit to TestFlight
eas submit --platform ios --profile production
```

TestFlight reviewers receive an email. Invite testers in App Store Connect
under the TestFlight tab.

---

## 5. Android Play Store distribution

```bash
cd packages/mobile

# Build a production AAB (Android App Bundle)
eas build --platform android --profile production

# Submit to Play Store internal track
eas submit --platform android --profile production
```

Requires a `service-account.json` Google Cloud service account with Play
Developer API access (create at console.cloud.google.com).

---

## 6. GitHub Releases APK

The `.github/workflows/mobile-preview.yml` workflow (stub) will:
1. Trigger on push to `main` with changes under `packages/mobile/**`.
2. Run `eas build --platform android --profile preview --non-interactive`.
3. Download the APK via the EAS API.
4. Upload it as a GitHub Release asset tagged `mobile-vX.Y.Z`.

Wire up the workflow by adding the following secrets to the repo:
- `EXPO_TOKEN` — an EAS personal access token (`eas token:create`)

---

## 7. App icons & splash screen

Source files are in `packages/mobile/assets/`:

| File | Usage |
|------|-------|
| `icon.png` | iOS home screen, 1024×1024 |
| `adaptive-icon.png` | Android adaptive icon foreground, 1024×1024 |
| `splash.png` | Splash screen, 1284×2778 (iPhone 12 Pro Max) |
| `notification-icon.png` | Android notification icon (white on transparent), 96×96 |

Source: copied from `web/static/icons/icon-512.png`. Run through
[Expo's icon generator](https://www.appicon.co/) or `npx expo-optimize`
to produce all required sizes.

---

## 8. OTA updates (Expo Updates)

Production builds include `expo-updates`. Push a JavaScript-only update
without going through the App Store:

```bash
eas update --branch production --message "Fix: chat load bug"
```

Native code changes (new Expo SDK, new native modules) still require a
full build + store submission.
