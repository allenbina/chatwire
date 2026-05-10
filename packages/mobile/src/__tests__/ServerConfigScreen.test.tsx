/**
 * Smoke test for ServerConfigScreen.
 * Verifies the form renders and the Connect button is present.
 */
import React from 'react'
import { render, fireEvent } from '@testing-library/react-native'

// Mock AsyncStorage
jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn().mockResolvedValue(null),
  setItem: jest.fn().mockResolvedValue(undefined),
  multiRemove: jest.fn().mockResolvedValue(undefined),
}))

// Mock expo-haptics
jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 0, Medium: 1, Heavy: 2 },
}))

// Mock @chatwire/shared
jest.mock('@chatwire/shared', () => ({
  ChaiwireClient: jest.fn().mockImplementation(() => ({
    healthz: jest.fn().mockResolvedValue(true),
  })),
  convRouteKey: jest.fn((c: { kind: string; handle?: string; guid?: string }) =>
    c.kind === 'group' ? c.guid : c.handle,
  ),
}))

// Mock navigation
const mockReplace = jest.fn()
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ replace: mockReplace }),
}))

import { ServerConfigScreen } from '../screens/ServerConfigScreen'
import { AppStateProvider } from '../state/AppStateContext'

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AppStateProvider>{children}</AppStateProvider>
}

const mockNavigation = { replace: mockReplace } as any
const mockRoute = { params: undefined } as any

describe('ServerConfigScreen', () => {
  it('renders the Connect button', () => {
    const { getByTestId, getByText } = render(
      <Wrapper>
        <ServerConfigScreen navigation={mockNavigation} route={mockRoute} />
      </Wrapper>,
    )
    expect(getByTestId('connect-button')).toBeTruthy()
    expect(getByText('Connect')).toBeTruthy()
  })

  it('renders URL and password inputs', () => {
    const { getByTestId } = render(
      <Wrapper>
        <ServerConfigScreen navigation={mockNavigation} route={mockRoute} />
      </Wrapper>,
    )
    expect(getByTestId('serverUrl-input')).toBeTruthy()
    expect(getByTestId('password-input')).toBeTruthy()
  })

  it('calls healthz on connect', async () => {
    const { ChaiwireClient } = require('@chatwire/shared')
    const mockHealthz = jest.fn().mockResolvedValue(true)
    ChaiwireClient.mockImplementation(() => ({ healthz: mockHealthz }))

    const { getByTestId } = render(
      <Wrapper>
        <ServerConfigScreen navigation={mockNavigation} route={mockRoute} />
      </Wrapper>,
    )
    fireEvent.press(getByTestId('connect-button'))
    // Allow async resolution
    await new Promise((r) => setTimeout(r, 50))
    expect(mockHealthz).toHaveBeenCalled()
  })
})
