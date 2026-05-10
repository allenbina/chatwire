# Repo Split Plan

> After the current loop run finishes, split into public + private repos.
> Goal: clean public repo with no internal dev state in history.

## What changes

| Before | After |
|--------|-------|
| `allenbina/chatwire` (public) — has HANDOFFs, loop scripts, wave docs in git history | `allenbina/chatwire` (public) — clean history, source code + user docs only |
| (nothing) | `allenbina/chatwire-dev` (private) — HANDOFFs, loop scripts, planning docs, greenfield analysis |

## Steps

### 1. Rename current repo

```
gh repo rename chatwire-dev
gh repo edit allenbina/chatwire-dev --visibility private
```

This frees up the `chatwire` name on GitHub.

### 2. Create fresh public repo

```bash
mkdir ~/git/chatwire-clean
cd ~/git/chatwire-clean
git init

# Copy source files only (no internal docs, no loop scripts)
rsync -av ~/git/chatwire/ . \
  --exclude='.git' \
  --exclude='docs/HANDOFF*.md' \
  --exclude='docs/greenfield-*.md' \
  --exclude='docs/repo-split-plan.md' \
  --exclude='scripts/chatwire-loop.sh' \
  --exclude='scripts/chain-waves.sh' \
  --exclude='scripts/wait_pypi.py' \
  --exclude='chatwire-plugins/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='web/frontend/node_modules/' \
  --exclude='web/frontend/dist/'

# Verify .gitignore includes the internal file patterns
# Initial commit with clean history
git add -A
git commit -m "Initial commit — chatwire v1.6.0 + React migration (Phase 1-3)"

gh repo create allenbina/chatwire --public --source=. --push
```

### 3. Update PyPI trusted publisher

Go to https://pypi.org/manage/project/chatwire/settings/publishing/
and update the trusted publisher entry:
- Repository: `allenbina/chatwire` (same name, but now points to new repo)
- Workflow: `publish.yml`
- Environment: `pypi`

No change needed since the repo name is the same — but verify it works
after the rename/recreate cycle.

### 4. Update .gitignore in new public repo

Add to .gitignore so internal files never accidentally get committed:

```
# Internal dev state (lives in chatwire-dev repo)
docs/HANDOFF*.md
scripts/chatwire-loop.sh
scripts/chain-waves.sh
scripts/wait_pypi.py
```

### 5. Update loop infrastructure in chatwire-dev

Update `chatwire-loop.sh` to work with the split:
- Loop reads HANDOFF.md from `chatwire-dev`
- Loop does its code work in a clone of public `chatwire`
- Loop pushes code changes to public `chatwire`
- Loop pushes HANDOFF updates to private `chatwire-dev`

Or simpler: keep the loop working in `chatwire-dev` (which has all the
code too), and we manually sync clean commits to the public repo. The
public repo is the "release" repo; dev happens in private.

### 6. Verify

- [ ] `pipx install chatwire` still works (PyPI is unaffected)
- [ ] `gh repo view allenbina/chatwire` shows clean history
- [ ] `gh repo view allenbina/chatwire-dev` is private
- [ ] Old GitHub Releases migrated or recreated on new repo
- [ ] Homebrew tap formula still points to correct repo
- [ ] README badges/links updated

## What about GitHub Releases + tags?

The old repo had tags (v0.2.0 through v1.6.0) and GitHub Releases
that the in-app update checker queries. Options:

1. **Recreate tags + releases on new repo** — `git tag` the matching
   commits, push tags, `gh release create` for each. The update
   checker queries `/releases/latest` so only the latest matters.

2. **Just tag the latest** — create v1.6.0 tag + release on the new
   repo. Older versions are on PyPI anyway. Users don't browse old
   releases.

Recommendation: option 2. Just tag the current version.

## What about Homebrew tap?

The tap formula has a `url` pointing to the PyPI sdist, not GitHub.
No change needed. If it points to GitHub archive URLs, update to the
new repo (same name, so probably no change).

## Timing

Do this after the current loop run finishes (session 3 of 3 is
in-flight). Don't interrupt the loop.
