const CACHE_NAME = 'ryubee-cache-v6-killswitch';

self.addEventListener('install', event => {
    // 即座にインストールして待機をスキップ
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    // 直ちに全クライアントの制御を奪う
    event.waitUntil(self.clients.claim());

    // 既存のすべてのキャッシュを強制削除する
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    console.log('Deleting cache:', cacheName);
                    return caches.delete(cacheName);
                })
            );
        })
    );
});

self.addEventListener('fetch', event => {
    // 何もインターセプトせず、完全にブラウザの標準ネットワーク通信に任せる
    // (FetchEvent.respondWithエラーを根本から絶つ)
    return;
});
