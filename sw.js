const CACHE_NAME = 'ryubee-cache-v3';
const urlsToCache = [
    './',
    './index.html',
    './volume.html',
    './jobs.html',
    './login.html',
    './settings.html',
    './invoice.html',
    './assets/css/style.css',
    './assets/js/api.js',
    './assets/js/utils.js',
    'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                return cache.addAll(urlsToCache);
            })
    );
});

self.addEventListener('fetch', event => {
    // 基本的にキャッシュ優先、なければネットワークへ（Network First or Cache First）
    // ここではStale-While-Revalidate的なシンプルな実装
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // キャッシュがあればそれを返す
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
    );
});

self.addEventListener('activate', event => {
    const cacheWhitelist = [CACHE_NAME];
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheWhitelist.indexOf(cacheName) === -1) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});
