// Ryu兵衛 for 山文 — Service Worker (v12: キャッシュ不整合・白画面防止強化)
const CACHE_NAME = 'ryubee-yamabun-v12';
const PRECACHE_URLS = [
    './',
    './index.html',
    './assets/css/style.css',
    './assets/js/api.js',
    './assets/js/utils.js',
    './assets/icons/icon-192.png',
    './assets/icons/icon-512.png'
];

// インストール時にキャッシュ（失敗しても停止しない安全設計）
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                return Promise.allSettled(
                    PRECACHE_URLS.map(url => cache.add(url).catch(() => {}))
                );
            })
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

// ネットワーク優先、フォールバックでキャッシュ（白画面防止）
self.addEventListener('fetch', event => {
    // API呼び出しはキャッシュしない（常にネットワーク通信）
    if (event.request.url.includes('/v1/')) return;

    event.respondWith(
        fetch(event.request)
            .then(response => {
                if (response.ok && event.request.method === 'GET') {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(async () => {
                const cached = await caches.match(event.request);
                if (cached) return cached;
                // キャッシュもない場合は再度通常フェッチを試みる（白画面エラーの回避）
                return fetch(event.request);
            })
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
