import type { ReactNode } from 'react'
import styles from './AppShell.module.css'

type AppShellProps = {
  children: ReactNode
  className?: string
  /** bleed = atmosphere; stage = edge-to-edge (welcome) */
  variant?: 'default' | 'bleed' | 'stage'
}

/** Full-viewport shell — mobile and desktop stretch to the screen. */
export function AppShell({ children, className, variant = 'default' }: AppShellProps) {
  return (
    <div
      className={[
        styles.root,
        variant === 'bleed' || variant === 'stage' ? styles.bleed : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div
        className={[styles.frame, variant === 'stage' ? styles.stage : '']
          .filter(Boolean)
          .join(' ')}
      >
        {children}
      </div>
    </div>
  )
}
