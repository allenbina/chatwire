import {
  CircleCheck,
  Info,
  LoaderCircle,
  OctagonX,
  TriangleAlert,
} from 'lucide-react'
import { Toaster as Sonner } from 'sonner'
import { THEME_MAP } from '../../themes'

type ToasterProps = React.ComponentProps<typeof Sonner>

/**
 * Sonner toaster wired to our runtime theme system.
 *
 * Reads the stored theme name from localStorage (same key used by useTheme)
 * and derives whether the current theme is light/dark.  Falls back to
 * "dark" (Dracula default) if nothing is stored yet.
 */
const Toaster = ({ ...props }: ToasterProps) => {
  const stored = typeof window !== 'undefined'
    ? (localStorage.getItem('chatwire-theme') ?? 'dracula')
    : 'dracula'
  const isLight = THEME_MAP[stored]?.isLight ?? false
  const scheme: ToasterProps['theme'] = isLight ? 'light' : 'dark'

  return (
    <Sonner
      theme={scheme}
      className="toaster group"
      icons={{
        success: <CircleCheck className="h-4 w-4" />,
        info: <Info className="h-4 w-4" />,
        warning: <TriangleAlert className="h-4 w-4" />,
        error: <OctagonX className="h-4 w-4" />,
        loading: <LoaderCircle className="h-4 w-4 animate-spin" />,
      }}
      toastOptions={{
        classNames: {
          toast:
            'group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg',
          description: 'group-[.toast]:text-muted-foreground',
          actionButton: 'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
          cancelButton: 'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
