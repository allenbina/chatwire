import React, { createContext, useContext, useState, useCallback } from 'react'
import { ChaiwireClient } from '@chatwire/shared'

interface AppState {
  client: ChaiwireClient | null
  serverUrl: string
  setServerUrl: (url: string, password?: string) => void
}

const AppStateContext = createContext<AppState>({
  client: null,
  serverUrl: '',
  setServerUrl: () => {},
})

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [serverUrl, setServerUrlState] = useState('')
  const [client, setClient] = useState<ChaiwireClient | null>(null)

  const setServerUrl = useCallback((url: string, password?: string) => {
    setServerUrlState(url)
    setClient(new ChaiwireClient({ baseUrl: url, credentials: password }))
  }, [])

  return (
    <AppStateContext.Provider value={{ client, serverUrl, setServerUrl }}>
      {children}
    </AppStateContext.Provider>
  )
}

export function useAppState() {
  return useContext(AppStateContext)
}
