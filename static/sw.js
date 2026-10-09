// MicroStock Service Worker
// Verzija — menjaj kad menjaš keš
const CACHE_VERSION = 'microstock-v2';   // bilo v1, sad v2
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

// Fajlovi koji se keširaju odmah pri instalaciji
const PRECACHE_URLS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/img/logo-icon.png',
  '/static/img/logo-wordmark.png',
  '/static/img/logo-icon-rgb.png',
  '/offline',
];

// INSTALL — keširaj osnovne fajlove
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('[SW] Precache greška:', err);
      });
    })
  );
  self.skipWaiting();
});

// ACTIVATE — obriši stare keševe
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((k) => k.startsWith('microstock-') && k !== STATIC_CACHE && k !== RUNTIME_CACHE)
          .map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// FETCH — strategija
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Preskoči non-GET i eksterne domene
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  // API pozivi — uvek sa mreže, ne keširaj
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }
  // Preskoči keširanje za set-language i set-currency (moraju uvek sa mreže)
  if (url.pathname.startsWith('/set-language/') ||
      url.pathname.startsWith('/set-currency/')) {
    event.respondWith(fetch(request));
    return;
  }

  // Preskoči keširanje za auth (login/logout)
  if (url.pathname.startsWith('/login') ||
      url.pathname.startsWith('/logout') ||
      url.pathname.startsWith('/admin/')) {
    event.respondWith(fetch(request));
    return;
  }
  // HTML stranice — network-first, fallback na offline
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => {
          return caches.match(request).then((cached) => cached || caches.match('/offline'));
        })
    );
    return;
  }

  // Statički fajlovi (CSS, JS, slike) — cache-first
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});