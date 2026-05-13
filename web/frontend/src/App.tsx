/**
 * App root: QueryClientProvider + BrowserRouter.
 *
 * Routes:
 *   /login        → LoginPage    (public — no auth required)
 *   /             → ChatPage (no handle — shows empty state)
 *   /chat/:handle → ChatPage (active conversation)
 *   /settings     → SettingsPage  (lazy-loaded)
 *   /popout       → PopoutPage    (lazy-loaded)
 *   *             → redirect to /
 *
 * SettingsPage and PopoutPage are lazy-loaded so they don't land in the
 * main bundle. The main bundle shrinks; each page gets its own chunk that
 * is only fetched on first visit.
 */
import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ChatPage } from './pages/ChatPage'
import { LoginPage } from './pages/LoginPage'
import { Toaster } from '@/components/ui/sonner'
import { DataWarningModal } from './components/DataWarningModal'

// Lazy chunks — split out of the main bundle
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
)
const PopoutPage = lazy(() =>
  import('./pages/PopoutPage').then((m) => ({ default: m.PopoutPage }))
)
const PluginsPage = lazy(() =>
  import('./pages/PluginsPage').then((m) => ({ default: m.PluginsPage }))
)
const LogsPage = lazy(() =>
  import('./pages/LogsPage').then((m) => ({ default: m.LogsPage }))
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Minimal fallback shown while lazy chunks load (usually <100 ms on a fast
// connection; visible mainly on first cold visit).
function PageLoading() {
  return (
    <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm animate-pulse">
      Loading&hellip;
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat/:handle" element={<ChatPage />} />
          <Route
            path="/settings"
            element={
              <Suspense fallback={<PageLoading />}>
                <SettingsPage />
              </Suspense>
            }
          />
          <Route
            path="/popout"
            element={
              <Suspense fallback={<PageLoading />}>
                <PopoutPage />
              </Suspense>
            }
          />
          <Route
            path="/plugins"
            element={
              <Suspense fallback={<PageLoading />}>
                <PluginsPage />
              </Suspense>
            }
          />
          <Route
            path="/logs"
            element={
              <Suspense fallback={<PageLoading />}>
                <LogsPage />
              </Suspense>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <DataWarningModal />
      <Toaster />
    </QueryClientProvider>
  )
}
