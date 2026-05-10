/**
 * Vitest unit tests for MediaGallery + Lightbox.
 *
 * Covers:
 *   - single image: renders gallery group + one clickable thumbnail
 *   - two images: renders 2 thumbnails
 *   - four images: renders exactly 4 thumbnails, no overflow badge
 *   - five images: renders 4 thumbnails with "+1" overflow badge on 4th cell
 *   - clicking a thumbnail opens the lightbox dialog
 *   - lightbox shows the correct image alt (Image N of M)
 *   - lightbox close button closes the dialog
 *   - Next button advances the image index
 *   - Prev button retreats the image index
 *   - ArrowRight key advances the image index
 *   - ArrowLeft key retreats the image index
 *   - single image: no prev/next buttons shown
 */
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { MediaGallery } from './MediaGallery'
import type { Attachment } from '../api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeImage(i: number): Attachment {
  return {
    path: `/data/img${i}.jpg`,
    name: `img${i}.jpg`,
    mime: 'image/jpeg',
    kind: 'image',
    ready: true,
    is_plugin: false,
    total_bytes: 0,
  }
}

const ONE = [makeImage(1)]
const TWO = [makeImage(1), makeImage(2)]
const FOUR = [1, 2, 3, 4].map(makeImage)
const FIVE = [1, 2, 3, 4, 5].map(makeImage)

// ---------------------------------------------------------------------------
// Gallery grid
// ---------------------------------------------------------------------------

describe('MediaGallery grid', () => {
  it('renders a gallery group with one thumbnail for a single image', () => {
    render(<MediaGallery images={ONE} senderName="Alice" />)
    expect(screen.getByRole('group', { name: /image gallery, 1 photo$/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /image sent by alice/i })).toHaveLength(1)
  })

  it('renders 2 thumbnails for two images', () => {
    render(<MediaGallery images={TWO} senderName="Bob" />)
    expect(screen.getAllByRole('button', { name: /image sent by bob/i })).toHaveLength(2)
  })

  it('renders 4 thumbnails and no overflow badge for exactly 4 images', () => {
    render(<MediaGallery images={FOUR} />)
    expect(screen.getAllByRole('button', { name: /image sent by you/i })).toHaveLength(4)
    expect(screen.queryByText(/^\+\d/)).toBeNull()
  })

  it('renders 4 thumbnails and a "+1" overflow badge for 5 images', () => {
    render(<MediaGallery images={FIVE} />)
    expect(screen.getAllByRole('button', { name: /image sent by you/i })).toHaveLength(4)
    expect(screen.getByText('+1')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Lightbox open / close
// ---------------------------------------------------------------------------

describe('Lightbox', () => {
  it('opens the lightbox when a thumbnail is clicked', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} senderName="Alice" />)
    const [first] = screen.getAllByRole('button', { name: /image sent by alice/i })
    await user.click(first)
    expect(
      screen.getByRole('dialog', { name: /image lightbox, 2 photos/i }),
    ).toBeInTheDocument()
  })

  it('lightbox shows "Image 1 of N" alt for the first image', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} />)
    await user.click(screen.getAllByRole('button', { name: /image sent by you/i })[0])
    const dialog = screen.getByRole('dialog', { name: /lightbox/i })
    expect(within(dialog).getByAltText('Image 1 of 2')).toBeInTheDocument()
  })

  it('close button dismisses the lightbox', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={ONE} />)
    await user.click(screen.getByRole('button', { name: /image sent by you/i }))
    expect(screen.getByRole('dialog', { name: /lightbox/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /close lightbox/i }))
    expect(screen.queryByRole('dialog', { name: /lightbox/i })).toBeNull()
  })

  it('single image: no prev/next buttons in lightbox', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={ONE} />)
    await user.click(screen.getByRole('button', { name: /image sent by you/i }))
    expect(screen.queryByRole('button', { name: /previous image/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /next image/i })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Prev / Next navigation
// ---------------------------------------------------------------------------

describe('Lightbox navigation', () => {
  it('Next button advances to the second image', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} />)
    await user.click(screen.getAllByRole('button', { name: /image sent by you/i })[0])
    const dialog = screen.getByRole('dialog', { name: /lightbox/i })
    expect(within(dialog).getByAltText('Image 1 of 2')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /next image/i }))
    expect(within(dialog).getByAltText('Image 2 of 2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /next image/i })).toBeNull()
  })

  it('Prev button retreats from the second image', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} />)
    // Open at index 1 (second thumbnail)
    await user.click(screen.getAllByRole('button', { name: /image sent by you/i })[1])
    const dialog = screen.getByRole('dialog', { name: /lightbox/i })
    expect(within(dialog).getByAltText('Image 2 of 2')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /previous image/i }))
    expect(within(dialog).getByAltText('Image 1 of 2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /previous image/i })).toBeNull()
  })

  it('ArrowRight key advances the image', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} />)
    await user.click(screen.getAllByRole('button', { name: /image sent by you/i })[0])
    const dialog = screen.getByRole('dialog', { name: /lightbox/i })
    expect(within(dialog).getByAltText('Image 1 of 2')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(within(dialog).getByAltText('Image 2 of 2')).toBeInTheDocument()
  })

  it('ArrowLeft key retreats the image', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} />)
    // Open at second image
    await user.click(screen.getAllByRole('button', { name: /image sent by you/i })[1])
    const dialog = screen.getByRole('dialog', { name: /lightbox/i })
    expect(within(dialog).getByAltText('Image 2 of 2')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(within(dialog).getByAltText('Image 1 of 2')).toBeInTheDocument()
  })

  it('ArrowLeft does not go below index 0', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} />)
    await user.click(screen.getAllByRole('button', { name: /image sent by you/i })[0])
    const dialog = screen.getByRole('dialog', { name: /lightbox/i })

    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    // Still on image 1
    expect(within(dialog).getByAltText('Image 1 of 2')).toBeInTheDocument()
  })

  it('ArrowRight does not exceed last index', async () => {
    const user = userEvent.setup()
    render(<MediaGallery images={TWO} />)
    await user.click(screen.getAllByRole('button', { name: /image sent by you/i })[1])
    const dialog = screen.getByRole('dialog', { name: /lightbox/i })

    fireEvent.keyDown(window, { key: 'ArrowRight' })
    // Still on image 2
    expect(within(dialog).getByAltText('Image 2 of 2')).toBeInTheDocument()
  })
})
