import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { BottomNav } from '@/components/BottomNav'
import { EveningDeskIllustration } from '@/components/EveningDeskIllustration'
import { fetchMe, type MeUser } from '@/lib/api'
import { isAuthenticated } from '@/lib/authStorage'
import { getDisplayName, isOnboardingDone } from '@/lib/session'
import styles from './DiaryHomePage.module.css'

const WEEK = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'] as const

export function DiaryHomePage() {
  const [me, setMe] = useState<MeUser | null>(null)

  useEffect(() => {
    if (!isAuthenticated()) return
    void fetchMe()
      .then(setMe)
      .catch(() => setMe(null))
  }, [])

  const name = getDisplayName() || me?.first_name || 'друг'
  const heading = useMemo(() => greetingForNow(name), [name])
  const dateLabel = useMemo(() => formatTodayLabel(), [])

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  if (!isOnboardingDone()) {
    return <Navigate to="/onboarding" replace />
  }

  return (
    <AppShell>
      <main className={styles.page}>
        <header className={styles.header}>
          <div>
            <p className={styles.date}>{dateLabel}</p>
            <h1 className={styles.hello}>{heading}</h1>
          </div>
          <button type="button" className={styles.bell} aria-label="Уведомления" disabled>
            <BellIcon />
          </button>
        </header>

        <section className={styles.hero}>
          <EveningDeskIllustration />
          <div className={styles.prompt}>
            <p className={styles.promptEyebrow}>Вопрос на вечер</p>
            <p className={styles.promptText}>Что хочется отпустить перед сном?</p>
            <Link to="/entries/new" className={styles.promptGo} aria-label="Ответить">
              →
            </Link>
          </div>
        </section>

        <section className={styles.week}>
          <div className={styles.weekHead}>
            <h2>Неделя</h2>
            <p>светлее огонёк — спокойнее день</p>
          </div>
          <div className={styles.orbs}>
            {WEEK.map((day, index) => (
              <div key={day} className={styles.orbItem}>
                <span
                  className={styles.orb}
                  style={{ background: orbColor(index) }}
                  aria-hidden="true"
                />
                <span>{day}</span>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.today}>
          <div className={styles.todayHead}>
            <h2>Сегодня</h2>
            <span>пока пусто</span>
          </div>
          <p className={styles.empty}>
            Нажмите карандаш внизу — первая запись откроет дневник.
          </p>
        </section>

        <section className={styles.actions}>
          <Link to="/progress" className={styles.card}>
            <span className={styles.cardLabel}>Задание</span>
            <p>Скоро появятся шаги от психолога</p>
          </Link>
          <Link to="/entries/new" className={styles.card}>
            <span className={styles.cardLabel}>Психолог</span>
            <p>Поговорить о том, что тревожит</p>
          </Link>
        </section>

        <BottomNav />
      </main>
    </AppShell>
  )
}

function greetingForNow(name: string): string {
  const hour = new Date().getHours()
  if (hour < 12) return `Доброе утро, ${name}`
  if (hour < 18) return `Добрый день, ${name}`
  return `Добрый вечер, ${name}`
}

function formatTodayLabel(): string {
  return new Intl.DateTimeFormat('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
    .format(new Date())
    .replace(/^./, (c) => c.toUpperCase())
}

function orbColor(index: number): string {
  const colors = [
    'rgba(229,196,159,0.55)',
    'rgba(163,177,138,0.55)',
    'rgba(201,163,160,0.5)',
    'rgba(229,196,159,0.35)',
    'rgba(163,177,138,0.4)',
    'rgba(201,163,160,0.35)',
    'rgba(229,196,159,0.7)',
  ]
  return colors[index % colors.length]
}

function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 9a6 6 0 1 1 12 0c0 4 1.5 5.5 1.5 5.5H4.5S6 13 6 9z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path d="M10 18a2 2 0 0 0 4 0" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  )
}
