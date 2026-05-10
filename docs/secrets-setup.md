# GitHub Secrets Setup

Required secrets for the publish pipeline (`publish.yml`) and Docker workflow
(`docker.yml`). Add all of these under:

**GitHub → repo → Settings → Secrets and variables → Actions → Repository secrets**

---

## 1. `HOMEBREW_TAP_TOKEN` (required for homebrew-bump job)

The `homebrew-bump` job (job 5 in `publish.yml`) pushes an updated
`Formula/chatwire.rb` directly to `allenbina/homebrew-tap`. The default
`GITHUB_TOKEN` is scoped to the current repo only, so a separate Personal
Access Token is required.

### Steps

1. Go to **GitHub → Settings → Developer settings → Personal access tokens →
   Tokens (classic)**.
2. Click **Generate new token (classic)**.
3. Set **Note**: `chatwire homebrew-tap push`
4. Set **Expiration**: 1 year (or "No expiration" — your call)
5. Under **Select scopes**, check only **`repo`** (full control of private
   repositories). This grants read+write to `allenbina/homebrew-tap`.
6. Click **Generate token** and copy it immediately.
7. In the `chatwire-dev` repo: **Settings → Secrets → Actions → New repository
   secret**
   - Name: `HOMEBREW_TAP_TOKEN`
   - Value: paste the token
8. Repeat step 7 for the public **`chatwire`** repo (the one that actually
   auto-triggers on `v*` tags).

### What it does

`dawidd6/action-homebrew-bump-formula@v3` checks out `allenbina/homebrew-tap`,
updates the `url` and `sha256` fields in `Formula/chatwire.rb` to match the
newly-released version, and pushes the commit directly (`push: true`). Without
this secret the job will fail at the authentication step; the other four jobs
(frontend build, Python build, PyPI publish, GitHub release) still succeed.

### Formula URL note

The current formula (`Formula/chatwire.rb`) uses a **GitHub archive URL**:

```
url "https://github.com/allenbina/chatwire/archive/refs/tags/vX.Y.Z.tar.gz"
```

The bump action detects this pattern and substitutes the new version tag and
recalculates the sha256 from the archive automatically. No extra configuration
is needed in `publish.yml`.

---

## 2. `PYPI_API_TOKEN` (required for publish-pypi job)

The `publish-pypi` job currently uses a PyPI API token (not OIDC trusted
publisher). Required for the public `chatwire` repo only — `chatwire-dev` has
`publish.yml` set to `workflow_dispatch` (manual only) and never auto-publishes.

### Steps

1. Go to **PyPI → Account → API tokens → Add API token**.
2. Set **Token name**: `chatwire GH Actions`
3. Set **Scope**: `Project: chatwire` (limit to this project, not entire account)
4. Copy the token (shown only once, starts with `pypi-`).
5. In the **public `chatwire` repo**: Settings → Secrets → Actions → New
   repository secret
   - Name: `PYPI_API_TOKEN`
   - Value: paste the token

### OIDC alternative (no secret needed)

You can eliminate the token entirely by switching to OIDC Trusted Publisher:

1. On PyPI: **Project chatwire → Settings → Publishing → Add a new publisher**
   - Owner: `allenbina`
   - Repository name: `chatwire`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
2. In `publish.yml`, replace the `publish-pypi` job's `password:` line with
   the OIDC step (see the comment block in the workflow file).

---

## 3. `EXPO_TOKEN` (required for mobile preview builds)

The `mobile-preview.yml` workflow builds an Android APK via EAS Build (Expo
Application Services) and uploads it as a workflow artifact. The EAS steps are
guarded by `if: env.EXPO_TOKEN != ''` — without this secret the `npm ci` and
print steps still run (workflow stays green) but no APK is produced.

### Prerequisites

Before adding the secret, the EAS project must be registered on expo.dev:

1. Install EAS CLI: `npm install -g eas-cli`
2. Log in: `eas login`
3. Inside `packages/mobile/`, run: `eas init`
   - This creates a real project on expo.dev and writes the UUID into
     `packages/mobile/app.json` under `extra.eas.projectId`.
   - Commit the updated `app.json` (the UUID is not secret).

### Steps

1. Generate a token: `eas token:create` (or **expo.dev → Account → Access Tokens
   → Create Token**). Select scope **"All access"** (EAS Build requires it).
2. Copy the token (shown only once, starts with `expo-`).
3. In the **`chatwire-dev`** repo: **Settings → Secrets → Actions → New
   repository secret**
   - Name: `EXPO_TOKEN`
   - Value: paste the token
4. (Optional) Repeat for the public `chatwire` repo if you add a production
   build workflow there later.

### What it does

When `EXPO_TOKEN` is set:
- `expo/expo-github-action@v8` logs in to EAS using the token.
- `eas build --platform android --profile preview --non-interactive` submits
  a cloud build to expo.dev and waits for the APK.
- `actions/upload-artifact@v4` attaches the APK to the workflow run
  (30-day retention) so reviewers can download and install it directly.

### iOS builds

iOS simulator builds require a macOS runner + Apple Developer account. That job
is left commented in `mobile-preview.yml`. Revisit when the Apple Developer
account is available (same account needed for Phase 7-2 macOS DMG).

---

## 4. No secret needed: Docker (`GITHUB_TOKEN`)

`docker.yml` authenticates to GHCR using the built-in `GITHUB_TOKEN`. No
additional secret is required. Ensure the repo has **Packages → Inherit
access from source repository** enabled under Settings → Actions → General
if the image visibility needs changing.

---

## Summary table

| Secret              | Repo(s)          | Purpose                        | Status           |
|---------------------|------------------|--------------------------------|------------------|
| `HOMEBREW_TAP_TOKEN`| chatwire + dev   | Bump brew formula on release   | **NOT YET ADDED**|
| `PYPI_API_TOKEN`    | chatwire (public)| Publish wheel to PyPI          | Assumed present  |
| `EXPO_TOKEN`        | chatwire-dev     | EAS Build Android APK preview  | **NOT YET ADDED**|
| *(none)*            | chatwire-dev     | Docker → GHCR via GITHUB_TOKEN | Built-in, works  |
