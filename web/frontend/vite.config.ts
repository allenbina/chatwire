import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: '/app/',
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      scope: '/app/',
      base: '/app/',
      filename: 'sw.js',
      manifest: {
        name: 'chatwire',
        short_name: 'chatwire',
        description: 'iMessage bridge web client',
        display: 'standalone',
        start_url: '/app/',
        scope: '/app/',
        theme_color: '#bd93f9',
        background_color: '#282a36',
        icons: [
          {
            src: 'icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: 'icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: 'icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        // Precache all built assets
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          // Message send — NetworkOnly + BackgroundSync so offline sends
          // are queued in IndexedDB and retried when connectivity returns.
          {
            urlPattern: /^\/send$/,
            handler: 'NetworkOnly',
            options: {
              backgroundSync: {
                name: 'chatwire-send-queue',
                options: {
                  maxRetentionTime: 24 * 60, // 24 hours (minutes)
                },
              },
            },
          },
          // API: conversations + messages — NetworkFirst (fresh data when
          // online, cached copy when offline)
          {
            urlPattern: /^\/api\/ui\/(conversations|messages)/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 60 * 60, // 1 hour
              },
              networkTimeoutSeconds: 5,
            },
          },
          // Built JS/CSS/images — CacheFirst (hashed filenames, safe to
          // serve from cache forever)
          {
            urlPattern: /\/app\/assets\/.+\.(js|css|png|svg|woff2)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'static-assets',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
              },
            },
          },
          // Avatars / attachments — StaleWhileRevalidate
          {
            urlPattern: /\/(avatar|attachment)/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'media-cache',
              expiration: {
                maxEntries: 200,
                maxAgeSeconds: 7 * 24 * 60 * 60,
              },
            },
          },
        ],
        // Offline fallback: serve the SPA shell when a navigation fails
        navigateFallback: '/app/index.html',
        navigateFallbackAllowlist: [/^\/app/],
      },
    }),
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    // In dev mode, proxy API and SSE calls to the running FastAPI server.
    proxy: {
      '/api': 'http://localhost:8723',
      '/events': 'http://localhost:8723',
      '/healthz': 'http://localhost:8723',
      '/login': 'http://localhost:8723',
      '/logout': 'http://localhost:8723',
    },
  },
})
