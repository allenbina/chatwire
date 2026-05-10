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

jest.mock('@chatwire/shared', () => ({
  ChaiwireClient: jest.fn().mockImplementation(() => ({
    getConversations: mockGetConversations,
    eventsUrl: jest.fn().mockReturnValue('http://localhost:8723/events'),
  })),
  convRouteKey: (c: { kind: string; handle?: string; guid?: string }) =>
    c.kind === 'group' ? c.guid : c.handle,
}))

// Mock navigation
const mockNavigate = jest.fn()
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}))

import { ConversationListScreen } from '../screens/ConversationListScreen'
import { AppStateProvider } from '../state/AppStateContext'

const mockNavigation = { navigate: mockNavigate } as any
const mockRoute = {} as any

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AppStateProvider>{children}</AppStateProvider>
}

describe('ConversationListScreen', () => {
  it('renders without crashing', () => {
    const { toJSON } = render(
      <Wrapper>
        <ConversationListScreen navigation={mockNavigation} route={mockRoute} />
      </Wrapper>,
    )
    expect(toJSON()).toBeTruthy()
  })

  it('shows conversation after loading', async () => {
    const { getByText } = render(
      <Wrapper>
        <ConversationListScreen navigation={mockNavigation} route={mockRoute} />
      </Wrapper>,
    )
    await waitFor(() => expect(getByText('Alice')).toBeTruthy())
  })
})
