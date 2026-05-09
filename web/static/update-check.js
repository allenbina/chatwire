// Update-check banner.
//
// On page load, ask the GitHub Releases API for the latest release of the
// configured repo. If its tag parses as a higher semver than the version
// the server reports in <meta name="app-version">, surface a banner with
// a link to the release notes.
//
// Skips entirely when:
//   - the local version contains "-dev" (you're on main; nothing to upgrade to)
//   - we checked successfully within the last 24h (cached in localStorage)
//   - the user dismissed *this specific newer version* (cached in localStorage —
//     a future, even-newer release will still trigger the banner)
//   - the GitHub API returns 404 (repo has no releases yet) or 403 (rate-limited)
//
// All failures are silent; the banner is informational, not load-bearing.

(function () {
  'use strict';

  const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24h
  const LS_LAST_CHECK = 'imb.updatecheck.lastCheckedAt';
  const LS_LAST_LATEST = 'imb.updatecheck.lastLatest';
  const LS_DISMISSED = 'imb.updatecheck.dismissed';

  function meta(name) {
    const el = document.querySelector('meta[name="' + name + '"]');
    return el ? (el.getAttribute('content') || '').trim() : '';
  }

  // Parse a tag like "v0.1.0", "0.2.0-rc1", or "1.2.3" into a comparable
  // tuple. Returns null on anything weird so we err on the side of *not*
  // showing a misleading banner.
  function parseSemver(s) {
    if (!s) return null;
    const m = String(s).trim().replace(/^v/i, '').match(/^(\d+)\.(\d+)\.(\d+)(?:[-+](.+))?$/);
    if (!m) return null;
    return {
      major: parseInt(m[1], 10),
      minor: parseInt(m[2], 10),
      patch: parseInt(m[3], 10),
      // Pre-release suffix: presence makes a version *less than* the same
      // numbers without a suffix (per semver). We don't compare suffix
      // contents — for our use it's always "is the latest *release* newer
      // than what's installed", and pre-releases are rare enough.
      pre: m[4] || '',
    };
  }

  // Returns true iff `latest` is strictly newer than `current`.
  function isNewer(latest, current) {
    if (!latest || !current) return false;
    if (latest.major !== current.major) return latest.major > current.major;
    if (latest.minor !== current.minor) return latest.minor > current.minor;
    if (latest.patch !== current.patch) return latest.patch > current.patch;
    // Same numeric tuple: a release without suffix beats one with.
    if (latest.pre === '' && current.pre !== '') return true;
    return false;
  }

  function showBanner(latestTag, releaseUrl) {
    if (!latestTag) return;
    const banner = document.getElementById('update-banner');
    if (!banner) return;
    const v = banner.querySelector('.update-banner-version');
    const a = banner.querySelector('.update-banner-link');
    if (v) v.textContent = latestTag;
    if (a) {
      const repo = meta('update-check-repo');
      const fallback = repo ? 'https://github.com/' + repo + '/releases' : '#';
      a.setAttribute('href', releaseUrl || fallback);
    }
    banner.hidden = false;
    document.body.classList.add('has-update-banner');

    const dismiss = banner.querySelector('.update-banner-dismiss');
    if (dismiss) {
      dismiss.addEventListener('click', function () {
        banner.hidden = true;
        document.body.classList.remove('has-update-banner');
        try {
          localStorage.setItem(LS_DISMISSED, latestTag);
        } catch (_) { /* storage disabled, fine */ }
      }, { once: true });
    }
  }

  async function check() {
    const localTag = meta('app-version');
    const repo = meta('update-check-repo');
    if (!localTag || !repo) return;
    if (localTag.indexOf('-dev') !== -1) return;

    const local = parseSemver(localTag);
    if (!local) return;

    // 24h cache: if we already have a known latest and we checked recently,
    // re-render from cache without hitting the API.
    let lastCheckedAt = 0;
    try { lastCheckedAt = parseInt(localStorage.getItem(LS_LAST_CHECK) || '0', 10) || 0; }
    catch (_) { /* no storage */ }

    let cached = null;
    try { cached = JSON.parse(localStorage.getItem(LS_LAST_LATEST) || 'null'); }
    catch (_) { /* malformed cache, drop it */ }

    let dismissed = '';
    try { dismissed = localStorage.getItem(LS_DISMISSED) || ''; }
    catch (_) { /* no storage */ }

    const fresh = (Date.now() - lastCheckedAt) < CHECK_INTERVAL_MS;

    if (fresh && cached && cached.tag) {
      const latest = parseSemver(cached.tag);
      if (isNewer(latest, local) && cached.tag !== dismissed) {
        showBanner(cached.tag, cached.url || '');
      }
      return;
    }

    // Hit the API.
    let resp;
    try {
      resp = await fetch('https://api.github.com/repos/' + encodeURI(repo) + '/releases/latest', {
        headers: { 'Accept': 'application/vnd.github+json' },
      });
    } catch (_) {
      return; // network failure; silent
    }

    // 404 = no releases yet (totally normal for a new repo). 403 = rate limit.
    // Either way, mark as checked so we don't hammer the API.
    if (resp.status === 404 || resp.status === 403) {
      try { localStorage.setItem(LS_LAST_CHECK, String(Date.now())); }
      catch (_) { /* no storage */ }
      return;
    }
    if (!resp.ok) return;

    let data;
    try { data = await resp.json(); }
    catch (_) { return; }

    const tag = (data && data.tag_name) || '';
    const url = (data && data.html_url) || ('https://github.com/' + repo + '/releases');
    if (!tag) return;

    try {
      localStorage.setItem(LS_LAST_CHECK, String(Date.now()));
      localStorage.setItem(LS_LAST_LATEST, JSON.stringify({ tag: tag, url: url }));
    } catch (_) { /* no storage */ }

    const latest = parseSemver(tag);
    if (isNewer(latest, local) && tag !== dismissed) {
      showBanner(tag, url);
    }
  }

  // Defer slightly so we don't fight the initial page paint or htmx swaps.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(check, 1500); });
  } else {
    setTimeout(check, 1500);
  }
})();
