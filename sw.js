// Ryu兵衛 for 山文 — Service Worker
const CACHE_NAME = 'ryubee-yamabun-v1';
const PRECACHE_URLS = [
    '/volume-tool-ryubee/',
    '/volume-tool-ryubee/index.html',
    '/volume-tool-ryubee/assets/css/style.css',
    '/volume-tool-ryubee/assets/js/api.js',
    '/volume-tool-ryubee/assets/js/utils.js',
    '/volume-tool-ryubee/assets/icons/icon-192.png',
    '/volume-tool-ryubee/assets/icons/icon-512.png'
];

// インストール時にキャッシュ
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting())
    );
});

// 古いキャッシュを削除
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

// ネットワーク優先、フォールバックでキャッシュ
self.addEventListener('fetch', event => {
    // API呼び出しはキャッシュしない
    if (event.request.url.includes('/v1/')) return;

    event.respondWith(
        fetch(event.request)
            .then(response => {
                // 成功したらキャッシュを更新
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});

// プッシュ通知の受信
self.addEventListener('push', event => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'Ryu兵衛 for 山文';
    const options = {
        body: data.body || '新しい通知があります',
        icon: '/volume-tool-ryubee/assets/icons/icon-192.png',
        badge: '/volume-tool-ryubee/assets/icons/icon-192.png',
        data: { url: data.url || '/volume-tool-ryubee/index.html' }
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

// 通知クリック時にアプリを開く
self.addEventListener('notificationclick', event => {
    event.notification.close();
    const url = event.notification.data?.url || '/volume-tool-ryubee/index.html';
    event.waitUntil(
        clients.matchAll({ type: 'window' }).then(windowClients => {
            for (const client of windowClients) {
                if (client.url.includes('volume-tool-ryubee') && 'focus' in client) {
                    return client.focus();
                }
            }
            return clients.openWindow(url);
        })
    );
});
