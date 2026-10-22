import { Link, useLocation } from 'react-router-dom'
import styles from './BottomNav.module.css'

const ITEMS = [
  { to: '/app', label: 'Дневник', icon: DiaryIcon },
  { to: '/archive', label: 'Архив', icon: ArchiveIcon },
  { to: '/progress', label: 'Прогресс', icon: ProgressIcon },
  { to: '/profile', label: 'Профиль', icon: ProfileIcon },
] as const

export function BottomNav() {
  const location = useLocation()

  return (
    <nav className={styles.nav} aria-label="Основная навигация">
      <div className={styles.row}>
        {ITEMS.slice(0, 2).map((item) => {
          const active = location.pathname.startsWith(item.to)
          const Icon = item.icon
          return (
            <Link
              key={item.to}
              to={item.to}
              className={active ? styles.itemActive : styles.item}
              aria-current={active ? 'page' : undefined}
            >
              <Icon />
              <span>{item.label}</span>
            </Link>
          )
        })}

        <Link to="/entries/new" className={styles.fab} aria-label="Новая запись">
          <PencilIcon />
        </Link>

        {ITEMS.slice(2).map((item) => {
          const active = location.pathname.startsWith(item.to)
          const Icon = item.icon
          return (
            <Link
              key={item.to}
              to={item.to}
              className={active ? styles.itemActive : styles.item}
              aria-current={active ? 'page' : undefined}
            >
              <Icon />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}

function DiaryIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="5" y="3" width="14" height="18" rx="2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M9 7h6M9 11h6M9 15h4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}

function ArchiveIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}

function ProgressIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 16c2-4 3-6 5-6s3 5 5 5 3-7 6-9"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  )
}

function ProfileIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M5 19c1.5-3.5 4-5 7-5s5.5 1.5 7 5"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  )
}

function PencilIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 19l1.2-4.5L16.5 4.2a2 2 0 0 1 2.8 2.8L9.5 16.8 5 19z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  )
}
