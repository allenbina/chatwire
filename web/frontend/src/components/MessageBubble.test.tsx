/**
 * Regression tests for Phase 18 bug fixes in MessageBubble.
 *
 * Covers:
 *   - Link preview card renders when msg.link_preview exists (#30)
 *   - Video attachment has onError → swaps to download link (#32)
 *   - Sent bubble has rounded-br-sm; received has rounded-bl-sm (#33)
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MessageBubble } from './MessageBubble'
import type { Message, Attachment } from '../api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMessage(overrides: Partial<Message> & { rowid: number }): Message {
  return {
    date: 1_000_000,
    text: '',
    from_me: false,
    ts: '12:00 PM',
    attachments: [],
    link_preview: null,
    service: 'iMessage',
    ...overrides,
  }
}

function makeVideoAtt(overrides?: Partial<Attachment>): Attachment {
  return {
    path: '/Library/video.mov',
    name: 'video.mov',
    mime: 'video/quicktime',
    kind: 'video',
    ready: true,
    is_plugin: false,
    total_bytes: 2_000_000,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MessageBubble', () => {
  it('renders a link preview card when msg.link_preview has url and domain', () => {
    const msg = makeMessage({
      rowid: 1,
      text: 'Check this out https://apple.com',
      link_preview: {
        url: 'https://apple.com',
        domain: 'apple.com',
        image_path: '/Library/Caches/preview.jpg',
      },
    })
    const { container } = render(<MessageBubble msg={msg} />)
    // PreviewCard renders an <a> pointing to the URL
    const previewLink = container.querySelector('a.block[href="https://apple.com"]')
    expect(previewLink).not.toBeNull()
    // domain label appears in the card (URL is stripped from bubble text; only domain shown)
    expect(screen.getByText('apple.com')).toBeInTheDocument()
    // the href on the anchor correctly points to the full URL
    expect(previewLink?.getAttribute('href')).toBe('https://apple.com')
  })

  it('does not render a link preview card when msg.link_preview is null', () => {
    const msg = makeMessage({ rowid: 2, text: 'Just a plain message', link_preview: null })
    const { container } = render(<MessageBubble msg={msg} />)
    // No anchor inside the bubble pointing to an external URL
    expect(container.querySelector('a[target="_blank"]')).toBeNull()
  })

  it('renders preview image via /attachment endpoint when image_path is set', () => {
    const msg = makeMessage({
      rowid: 3,
      link_preview: { url: 'https://example.com', image_path: '/Library/preview.jpg' },
    })
    const { container } = render(<MessageBubble msg={msg} />)
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    expect(img!.getAttribute('src')).toContain('/attachment?path=')
    expect(img!.getAttribute('src')).toContain('size=thumb')
  })

  it('video attachment renders a <video> element with an onError handler', () => {
    const msg = makeMessage({ rowid: 4, attachments: [makeVideoAtt()] })
    const { container } = render(<MessageBubble msg={msg} />)
    const video = container.querySelector('video')
    expect(video).not.toBeNull()
    // Trigger error — VideoAttachment swaps to a download link
    fireEvent.error(video!)
    expect(container.querySelector('video')).toBeNull()
    const link = container.querySelector('a[download]')
    expect(link).not.toBeNull()
    expect(link!.getAttribute('href')).toContain('/attachment?path=')
  })

  it('sent bubble uses theme CSS variables for radius (tail on bottom-right)', () => {
    const msg = makeMessage({ rowid: 5, text: 'Sent by me', from_me: true })
    const { container } = render(<MessageBubble msg={msg} />)
    // The text bubble div gets inline styles referencing CSS variables
    const bubble = container.querySelector('[style]')
    expect(bubble).not.toBeNull()
    const style = bubble!.getAttribute('style')!
    expect(style).toContain('--radius-bubble')
    expect(style).toContain('--font-size-message')
    expect(style).toContain('border-bottom-right-radius')
    expect(style).toContain('--bubble-tail')
  })

  it('received bubble uses theme CSS variables for radius (tail on bottom-left)', () => {
    const msg = makeMessage({ rowid: 6, text: 'Received message', from_me: false })
    const { container } = render(<MessageBubble msg={msg} />)
    const bubble = container.querySelector('[style]')
    expect(bubble).not.toBeNull()
    const style = bubble!.getAttribute('style')!
    expect(style).toContain('--radius-bubble')
    expect(style).toContain('border-bottom-left-radius')
    expect(style).toContain('--bubble-tail')
  })

  // ---------------------------------------------------------------------------
  // Theme variable consumption — ensures components actually use CSS vars
  // ---------------------------------------------------------------------------

  it('bubble font size references --font-size-message (not hardcoded text-sm)', () => {
    const msg = makeMessage({ rowid: 7, text: 'Variable-driven', from_me: true })
    const { container } = render(<MessageBubble msg={msg} />)
    const bubble = container.querySelector('[style]')
    expect(bubble).not.toBeNull()
    const style = bubble!.getAttribute('style')!
    expect(style).toContain('font-size: var(--font-size-message)')
    // Must NOT have the hardcoded text-sm class on the bubble
    expect(bubble!.classList.contains('text-sm')).toBe(false)
  })

  it('bubble shadow references --bubble-shadow (not hardcoded)', () => {
    const msg = makeMessage({ rowid: 8, text: 'Shadow test', from_me: false })
    const { container } = render(<MessageBubble msg={msg} />)
    const bubble = container.querySelector('[style]')
    const style = bubble!.getAttribute('style')!
    expect(style).toContain('--bubble-shadow')
  })

  // ---------------------------------------------------------------------------
  // DeliveryBadge — SMS "sent" should be hidden
  // ---------------------------------------------------------------------------

  it('hides "sent" delivery badge on SMS messages', () => {
    const msg = makeMessage({ rowid: 9, text: 'SMS sent', from_me: true, service: 'SMS', status: 'sent' })
    const { container } = render(<MessageBubble msg={msg} />)
    // Should NOT render any badge with "sent" text
    expect(container.querySelector('[class*="badge"]')).toBeNull()
    expect(screen.queryByText('sent')).toBeNull()
  })

  it('shows "sent" delivery badge on iMessage (not yet delivered)', () => {
    const msg = makeMessage({ rowid: 10, text: 'iMessage sent', from_me: true, service: 'iMessage', status: 'sent' })
    render(<MessageBubble msg={msg} />)
    expect(screen.getByText('sent')).toBeInTheDocument()
  })

  it('shows "failed" delivery badge regardless of service', () => {
    const msg = makeMessage({ rowid: 11, text: 'Failed', from_me: true, service: 'SMS', status: 'failed' })
    render(<MessageBubble msg={msg} />)
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // ReplyQuote — iOS-style ghost bubble
  // ---------------------------------------------------------------------------

  it('renders ghost bubble with sender label and preview text for a reply (group chat)', () => {
    const msg = makeMessage({
      rowid: 12,
      text: 'My reply',
      from_me: true,
      reply_to: { rowid: 5, text: 'Parent message text', sender: 'Alice' },
    })
    // isGroup=true: sender label is shown in group chats
    render(<MessageBubble msg={msg} isGroup={true} />)
    // Ghost bubble shows the sender label
    expect(screen.getByText('Alice')).toBeInTheDocument()
    // Ghost bubble shows the parent text
    expect(screen.getByText('Parent message text')).toBeInTheDocument()
  })

  it('shows "You" as sender label when reply_to.sender is empty (parent from me, group chat)', () => {
    const msg = makeMessage({
      rowid: 13,
      text: 'Continuing my thread',
      from_me: true,
      reply_to: { rowid: 3, text: 'My earlier message', sender: '' },
    })
    // isGroup=true: "You" label is shown in group chats
    render(<MessageBubble msg={msg} isGroup={true} />)
    expect(screen.getByText('You')).toBeInTheDocument()
    expect(screen.getByText('My earlier message')).toBeInTheDocument()
  })

  it('shows fallback photo label when reply_to has no text and no image_path', () => {
    const msg = makeMessage({
      rowid: 14,
      text: 'Replied to a photo',
      from_me: false,
      reply_to: { rowid: 7, text: '', sender: 'Bob' },
    })
    render(<MessageBubble msg={msg} />)
    expect(screen.getByText('🖼️ Photo')).toBeInTheDocument()
  })

  it('renders a thumbnail img when reply_to has image_path', () => {
    const msg = makeMessage({
      rowid: 15,
      text: 'Replied with image',
      from_me: true,
      reply_to: { rowid: 8, text: '', sender: 'Carol', image_path: '/Library/photo.jpg' },
    })
    const { container } = render(<MessageBubble msg={msg} />)
    const thumb = container.querySelector('img[alt="Photo"]')
    expect(thumb).not.toBeNull()
    expect(thumb!.getAttribute('src')).toContain('/attachment?path=')
    expect(thumb!.getAttribute('src')).toContain('size=thumb')
  })

  it('ghost bubble has accessible aria-label describing the reply context', () => {
    const msg = makeMessage({
      rowid: 16,
      text: 'Reply',
      from_me: true,
      reply_to: { rowid: 9, text: 'Original text', sender: 'Dave' },
    })
    render(<MessageBubble msg={msg} />)
    const ghostBtn = screen.getByRole('button', { name: /Reply to Dave/i })
    expect(ghostBtn).toBeInTheDocument()
  })

  it('calls onScrollToRowid with the parent rowid when ghost bubble is clicked', () => {
    const onScroll = vi.fn()
    const msg = makeMessage({
      rowid: 17,
      text: 'A reply',
      from_me: false,
      reply_to: { rowid: 42, text: 'The original', sender: 'Eve' },
    })
    render(<MessageBubble msg={msg} onScrollToRowid={onScroll} />)
    const ghostBtn = screen.getByRole('button', { name: /Reply to Eve/i })
    fireEvent.click(ghostBtn)
    expect(onScroll).toHaveBeenCalledWith(42)
  })

  // ---------------------------------------------------------------------------
  // Reply ghost bubble sender-name visibility (#69)
  // ---------------------------------------------------------------------------

  it('hides sender name in ghost bubble for 1:1 threads (isGroup=false)', () => {
    const msg = makeMessage({
      rowid: 18,
      text: 'Reply in 1:1',
      from_me: false,
      reply_to: { rowid: 10, text: 'Original', sender: 'Frank' },
    })
    render(<MessageBubble msg={msg} isGroup={false} />)
    // aria-label still identifies the reply context
    expect(screen.getByRole('button', { name: /Reply to Frank/i })).toBeInTheDocument()
    // but the sender name paragraph should NOT be rendered
    expect(screen.queryByText('Frank')).toBeNull()
  })

  it('shows sender name in ghost bubble for group chats (isGroup=true)', () => {
    const msg = makeMessage({
      rowid: 19,
      text: 'Reply in group',
      from_me: false,
      reply_to: { rowid: 11, text: 'Group original', sender: 'Grace' },
    })
    render(<MessageBubble msg={msg} isGroup={true} />)
    expect(screen.getByRole('button', { name: /Reply to Grace/i })).toBeInTheDocument()
    // sender name label should be visible
    expect(screen.getByText('Grace')).toBeInTheDocument()
  })

  it('hides "You" label in ghost bubble for own replies in 1:1 threads', () => {
    const msg = makeMessage({
      rowid: 20,
      text: 'Reply to own msg in 1:1',
      from_me: false,
      // sender '' means the original was from me
      reply_to: { rowid: 12, text: 'I said this', sender: '' },
    })
    render(<MessageBubble msg={msg} isGroup={false} />)
    expect(screen.queryByText('You')).toBeNull()
  })

  it('shows "You" label in ghost bubble for own replies in group chats', () => {
    const msg = makeMessage({
      rowid: 21,
      text: 'Reply to own msg in group',
      from_me: false,
      reply_to: { rowid: 13, text: 'I said this', sender: '' },
    })
    render(<MessageBubble msg={msg} isGroup={true} />)
    expect(screen.getByText('You')).toBeInTheDocument()
  })

  it('defaults to hiding sender name when isGroup is omitted', () => {
    const msg = makeMessage({
      rowid: 22,
      text: 'Reply default',
      from_me: false,
      reply_to: { rowid: 14, text: 'Default case', sender: 'Hank' },
    })
    render(<MessageBubble msg={msg} />)
    expect(screen.queryByText('Hank')).toBeNull()
  })
})
