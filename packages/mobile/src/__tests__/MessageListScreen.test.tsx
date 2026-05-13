/**
 * Tests for MessageListScreen.
 *
 * Covers:
 *  - Loading indicator shown initially
 *  - Messages rendered after load
 *  - getMessages called on mount with handle + isGroup
 *  - loadingOlder indicator shown during back-pagination
 *  - onEndReached triggers getOlderMessages
 *  - Long-press on iOS shows ActionSheetIOS
 *  - Long-press on Android shows Alert
 */
import React from 'react'
import { Platform } from 'react-native'
import { render, waitFor, fireEvent } from '@testing-library/react-native'

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn().mockResolvedValue(null),
  setItem: jest.fn(),
}))

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 0, Medium: 1 },
}))

// Minimal message fixtures
const MSG_1 = {
  rowid: 1,
  date: 1000,
  from_me: false,
  ts: '10:00',
  text: 'Hello world',
  attachments: [],
  link_preview: null,
}
const MSG_OLD = {
  rowid: 0,
  date: 500,
  from_me: false,
  ts: '09:59',
  text: 'Older message',
  attachments: [],
  link_preview: null,
}

const mockGetMessages = jest.fn().mockResolvedValue({ messages: [MSG_1], has_more: false })
const mockGetOlderMessages = jest.fn().mockResolvedValue({ messages: [MSG_OLD], has_more: false })
const mockSendMessage = jest.fn().mockResolvedValue(undefined)

const mockClient = {
  getMessages: mockGetMessages,
  getOlderMessages: mockGetOlderMessages,
  sendMessage: mockSendMessage,
  eventsUrl: jest.fn().mockReturnValue('http://localhost:8723/events'),
  attachmentUrl: jest.fn((p: string) => p),
}

jest.mock('@chatwire/shared', () => ({
  ChaiwireClient: jest.fn().mockImplementation(() => mockClient),
  convRouteKey: jest.fn((c: { kind: string; handle?: string; guid?: string }) =>
    c.kind === 'group' ? c.guid : c.handle,
  ),
}))

jest.mock('../state/AppStateContext', () => ({
  useAppState: () => ({
    client: mockClient,
    serverUrl: 'http://localhost:8723',
    setServerUrl: jest.fn(),
  }),
  AppStateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Stub useServerEvents — no real SSE in unit tests
jest.mock('../hooks/useServerEvents', () => ({
  useServerEvents: jest.fn(),
}))

// Mock ComposeBox and MessageBubble to keep render lightweight
jest.mock('../components/ComposeBox', () => ({
  ComposeBox: ({ onSend }: { onSend: (t: string) => void }) => {
    const { TouchableOpacity, Text } = require('react-native')
    return (
      <TouchableOpacity testID="compose-send" onPress={() => onSend('test')}>
        <Text>Send</Text>
      </TouchableOpacity>
    )
  },
}))

jest.mock('../components/MessageBubble', () => ({
  MessageBubble: ({
    message,
    onLongPress,
  }: {
    message: { text: string }
    onLongPress: () => void
  }) => {
    const { TouchableOpacity, Text } = require('react-native')
    return (
      <TouchableOpacity testID={`msg-${message.text}`} onLongPress={onLongPress}>
        <Text>{message.text}</Text>
      </TouchableOpacity>
    )
  },
}))

import { MessageListScreen } from '../screens/MessageListScreen'

const mockRoute = {
  params: { handle: '+15005550001', name: 'Alice', isGroup: false },
} as any
const mockNavigation = {} as any

beforeEach(() => {
  jest.clearAllMocks()
  mockGetMessages.mockResolvedValue({ messages: [MSG_1], has_more: false })
  mockGetOlderMessages.mockResolvedValue({ messages: [MSG_OLD], has_more: false })
})

describe('MessageListScreen', () => {
  it('renders without crashing', () => {
    const { toJSON } = render(
      <MessageListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    expect(toJSON()).toBeTruthy()
  })

  it('shows loading indicator before messages load', () => {
    // Freeze in loading state with an unresolved promise
    mockGetMessages.mockReturnValueOnce(new Promise(() => {}))
    const { getByTestId } = render(
      <MessageListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    expect(getByTestId('loading-indicator')).toBeTruthy()
  })

  it('calls getMessages on mount with handle and isGroup', async () => {
    render(<MessageListScreen navigation={mockNavigation} route={mockRoute} />)
    await waitFor(() => expect(mockGetMessages).toHaveBeenCalledTimes(1))
    expect(mockGetMessages).toHaveBeenCalledWith('+15005550001', { isGroup: false })
  })

  it('renders messages after load', async () => {
    const { getByText } = render(
      <MessageListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    await waitFor(() => expect(getByText('Hello world')).toBeTruthy())
  })

  it('shows loadingOlder indicator while fetching older messages', async () => {
    mockGetMessages.mockResolvedValueOnce({ messages: [MSG_1], has_more: true })
    mockGetOlderMessages.mockReturnValueOnce(new Promise(() => {})) // freeze

    const { getByTestId, queryByTestId } = render(
      <MessageListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    // Wait for initial load to complete (loading-indicator disappears)
    await waitFor(() => expect(queryByTestId('loading-indicator')).toBeNull())

    // Simulate reaching the top of the (inverted) list
    fireEvent(getByTestId('message-list'), 'onEndReached')
    await waitFor(() => expect(queryByTestId('loading-older')).toBeTruthy())
  })

  it('calls getOlderMessages when list reaches the end and has_more is true', async () => {
    mockGetMessages.mockResolvedValueOnce({ messages: [MSG_1], has_more: true })

    const { getByTestId, queryByTestId } = render(
      <MessageListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    await waitFor(() => expect(queryByTestId('loading-indicator')).toBeNull())

    fireEvent(getByTestId('message-list'), 'onEndReached')
    await waitFor(() => expect(mockGetOlderMessages).toHaveBeenCalledTimes(1))
    expect(mockGetOlderMessages).toHaveBeenCalledWith('+15005550001', {
      isGroup: false,
      beforeDate: MSG_1.date,
      beforeRowid: MSG_1.rowid,
    })
  })

  it('shows ActionSheetIOS on long-press on iOS', async () => {
    const { ActionSheetIOS } = require('react-native')
    // Override impl to prevent native invariant throw in test env
    const showSpy = jest
      .spyOn(ActionSheetIOS, 'showActionSheetWithOptions')
      .mockImplementation(jest.fn())
    Object.defineProperty(Platform, 'OS', { value: 'ios', configurable: true })

    const { getByTestId, queryByTestId } = render(
      <MessageListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    await waitFor(() => expect(queryByTestId('loading-indicator')).toBeNull())

    fireEvent(getByTestId('msg-Hello world'), 'onLongPress')
    expect(showSpy).toHaveBeenCalled()

    Object.defineProperty(Platform, 'OS', { value: 'ios', configurable: true })
    showSpy.mockRestore()
  })

  it('shows Alert on long-press on Android', async () => {
    const { Alert } = require('react-native')
    const alertSpy = jest.spyOn(Alert, 'alert')
    Object.defineProperty(Platform, 'OS', { value: 'android', configurable: true })

    const { getByTestId, queryByTestId } = render(
      <MessageListScreen navigation={mockNavigation} route={mockRoute} />,
    )
    await waitFor(() => expect(queryByTestId('loading-indicator')).toBeNull())

    fireEvent(getByTestId('msg-Hello world'), 'onLongPress')
    expect(alertSpy).toHaveBeenCalledWith('Message', MSG_1.text, expect.any(Array))

    Object.defineProperty(Platform, 'OS', { value: 'ios', configurable: true })
    alertSpy.mockRestore()
  })
})
