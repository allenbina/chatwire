/**
 * Smoke test for ConversationListScreen.
 */
import React from 'react'
import { render, waitFor } from '@testing-library/react-native'

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn().mockResolvedValue('http://localhost:8723'),
  setItem: jest.fn(),
}))

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 0, Medium: 1 },
}))

const mockGetConversations = jest.fn().mockResolvedValue([
  {
    kind: 'handle',
    handle: '+15005550001',
    name: 'Alice',
    preview: 'Hey there!',
    has_media: false,
    last_dt: 1000,
    n: 2,
    all_handles: ['+15005550001'],
    is_favorite: false,
    last: '5m',
  },
])

// Build mockClient at module scope so it can be referenced inside jest.mock factories.
// Using var to avoid the temporal dead zone issue with hoisted jest.mock calls.
// eslint-disable-next-line no-var
var mockClient = {
  getConversations: mockGetConversations,
  eventsUrl: jest.fn().mockReturnValue('http://localhost:8723/events'),
}

jest.mock('@chatwire/shared', () => ({
  ChaiwireClient: jest.fn().mockImplementation(() => mockClient),
  convRouteKey: (c: { kind: string; handle?: string; guid?: string }) =>
    c.kind === 'group' ? c.guid : c.handle,
}))

// Provide a client directly so the screen's load() doesn't early-return
jest.mock('../state/AppStateContext', () => ({
  useAppState: () => ({
    client: mockClient,
    serverUrl: 'http://localhost:8723',
    setServerUrl: jest.fn(),
  }),
  AppStateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock navigation
const mockNavigate = jest.fn()
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}))

import { ConversationListScreen } from '../screens/ConversationListScreen'

const mockNavigation = { navigate: mockNavigate } as any
const mockRoute = {} as any

describe('ConversationListScreen', () => {
  it('renders without crashing', () => {
    const { toJSON } = render(
      <ConversationListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    expect(toJSON()).toBeTruthy()
  })

  it('shows conversation after loading', async () => {
    const { getByText } = render(
      <ConversationListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    await waitFor(() => expect(getByText('Alice')).toBeTruthy())
  })
})
