/**
 * Tests for SettingsScreen.
 *
 * Covers:
 *  - Renders server URL from AppState
 *  - Shows '—' placeholder when serverUrl is empty
 *  - Renders haptic feedback toggle
 *  - Renders static About rows (version + platform)
 *  - Disconnect row triggers Alert.alert
 *  - Confirming disconnect calls AsyncStorage.multiRemove and navigates to ServerConfig
 */
import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react-native'
import { Alert } from 'react-native'

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn().mockResolvedValue(null),
  setItem: jest.fn().mockResolvedValue(undefined),
  multiRemove: jest.fn().mockResolvedValue(undefined),
}))

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 0, Medium: 1 },
}))

const mockReplace = jest.fn()
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ replace: mockReplace }),
}))

// Default mock: serverUrl is set
const mockSetServerUrl = jest.fn()
let mockServerUrl = 'http://192.168.1.10:8723'

jest.mock('../state/AppStateContext', () => ({
  useAppState: () => ({
    client: null,
    serverUrl: mockServerUrl,
    setServerUrl: mockSetServerUrl,
  }),
  AppStateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import { SettingsScreen } from '../screens/SettingsScreen'

beforeEach(() => {
  jest.clearAllMocks()
  mockServerUrl = 'http://192.168.1.10:8723'
})

describe('SettingsScreen', () => {
  it('renders without crashing', () => {
    const { toJSON } = render(<SettingsScreen />)
    expect(toJSON()).toBeTruthy()
  })

  it('displays the server URL', () => {
    const { getByText } = render(<SettingsScreen />)
    expect(getByText('http://192.168.1.10:8723')).toBeTruthy()
  })

  it("shows '—' when serverUrl is empty", () => {
    mockServerUrl = ''
    const { getByText } = render(<SettingsScreen />)
    expect(getByText('—')).toBeTruthy()
  })

  it('renders the Haptic feedback label', () => {
    const { getByText } = render(<SettingsScreen />)
    expect(getByText('Haptic feedback')).toBeTruthy()
  })

  it('renders the app version row', () => {
    const { getByText } = render(<SettingsScreen />)
    expect(getByText('App version')).toBeTruthy()
    expect(getByText('1.0.0')).toBeTruthy()
  })

  it('renders the platform row', () => {
    const { getByText } = render(<SettingsScreen />)
    expect(getByText('Platform')).toBeTruthy()
    expect(getByText('Expo / React Native')).toBeTruthy()
  })

  it('pressing Disconnect shows Alert.alert', () => {
    const alertSpy = jest.spyOn(Alert, 'alert')
    const { getByText } = render(<SettingsScreen />)
    fireEvent.press(getByText('Disconnect'))
    expect(alertSpy).toHaveBeenCalledWith(
      'Disconnect',
      expect.any(String),
      expect.any(Array),
    )
    alertSpy.mockRestore()
  })

  it('confirming Disconnect calls AsyncStorage.multiRemove and navigates to ServerConfig', async () => {
    const AsyncStorage = require('@react-native-async-storage/async-storage')
    let confirmAction: (() => void) | undefined
    jest.spyOn(Alert, 'alert').mockImplementationOnce((_title, _msg, buttons) => {
      const destructive = (buttons as any[]).find((b) => b.style === 'destructive')
      confirmAction = destructive?.onPress
    })

    const { getByText } = render(<SettingsScreen />)
    fireEvent.press(getByText('Disconnect'))

    expect(confirmAction).toBeDefined()
    confirmAction!()

    await waitFor(() => {
      expect(AsyncStorage.multiRemove).toHaveBeenCalledWith(['serverUrl', 'serverPassword'])
      expect(mockReplace).toHaveBeenCalledWith('ServerConfig')
    })
  })
})
