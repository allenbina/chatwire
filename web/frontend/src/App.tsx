/**
 * App root: QueryClientProvider + BrowserRouter.
 *
 * Routes:
 *   /app/           → ChatPage (no handle — shows empty state)
 *   /app/chat/:handle → ChatPage (active conversation)
 *   /app/settings   → SettingsPage
 *   *               → redirect to /app/
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ChatPage } from './pages/ChatPage'
import { SettingsPage } from './pages/SettingsPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/app">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat/:handle" element={<ChatPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
