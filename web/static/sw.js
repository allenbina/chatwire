// Service worker: receives web-push events and surfaces OS notifications
// even when the tab is closed. Click handling focuses an existing tab
// (asking it to open the conversation) or opens a fresh one at
// /?open=<handle> or /?openChat=<guid>.

self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {}
  const title = data.title || 'iMessage';
  const options = {
    body: data.body || '',
    tag: data.tag || 'imessage',
    data: { handle: data.handle || '', chat: data.chat || '' },
    icon: '/static/favicon.svg',
    badge: '/static/favicon.svg',
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const d = event.notification.data || {};
  const handle = d.handle || '';
  const chat = d.chat || '';
  event.waitUntil((async () => {
    const wins = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const w of wins) {
      if (w.url.startsWith(self.registration.scope) || w.url.includes(location.host)) {
        await w.focus();
        if (chat) w.postMessage({ type: 'open_chat', chat });
        else if (handle) w.postMessage({ type: 'open_handle', handle });
        return;
      }
    }
    let url = '/';
    if (chat) url = `/?openChat=${encodeURIComponent(chat)}`;
    else if (handle) url = `/?open=${encodeURIComponent(handle)}`;
    await clients.openWindow(url);
  })());
});
