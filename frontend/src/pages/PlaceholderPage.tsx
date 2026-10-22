import { Link, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { BottomNav } from '@/components/BottomNav'
import { isAuthenticated } from '@/lib/authStorage'
import { isOnboardingDone } from '@/lib/session'
import styles from './PlaceholderPage.module.css'

type PlaceholderPageProps = {
  title: string
  note: string
  showNav?: boolean
}

export function PlaceholderPage({ title, note, showNav = true }: PlaceholderPageProps) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  if (!isOnboardingDone()) {
    return <Navigate to="/onboarding" replace />
  }

  return (
    <AppShell>
      <main className={styles.page}>
        <Link to="/app" className={styles.back}>
          ← Дневник
        </Link>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.note}>{note}</p>
        {showNav ? <BottomNav /> : null}
      </main>
    </AppShell>
  )
}
