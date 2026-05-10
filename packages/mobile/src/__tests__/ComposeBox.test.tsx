/**
 * Smoke test for ComposeBox.
 */
import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react-native'

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Light: 0, Medium: 1 },
}))

import { ComposeBox } from '../components/ComposeBox'

describe('ComposeBox', () => {
  it('renders the compose input', () => {
    const { getByTestId } = render(<ComposeBox onSend={jest.fn()} />)
    expect(getByTestId('compose-input')).toBeTruthy()
  })

  it('send button is disabled when input is empty', () => {
    const { getByTestId } = render(<ComposeBox onSend={jest.fn()} />)
    const btn = getByTestId('send-button')
    expect(btn.props.accessibilityState?.disabled).toBe(true)
  })

  it('calls onSend with trimmed text', async () => {
    const onSend = jest.fn().mockResolvedValue(undefined)
    const { getByTestId } = render(<ComposeBox onSend={onSend} />)
    fireEvent.changeText(getByTestId('compose-input'), '  Hello world  ')
    fireEvent.press(getByTestId('send-button'))
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('Hello world'))
  })

  it('clears input after send', async () => {
    const onSend = jest.fn().mockResolvedValue(undefined)
    const { getByTestId } = render(<ComposeBox onSend={onSend} />)
    const input = getByTestId('compose-input')
    fireEvent.changeText(input, 'Hi')
    fireEvent.press(getByTestId('send-button'))
    await waitFor(() => expect(input.props.value).toBe(''))
  })
})
