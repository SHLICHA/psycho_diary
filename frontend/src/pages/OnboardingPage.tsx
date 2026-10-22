import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { Button } from '@/components/ui/Button'
import {
  ApiError,
  acceptOnboardingAgreement,
  confirmCityTimezone,
  fetchProfileId,
  guessTimezoneFromCity,
  lookupCityTimezone,
  patchProfile,
  patchReminders,
  setOnboardingTimezone,
} from '@/lib/api'
import { isAuthenticated } from '@/lib/authStorage'
import {
  markOnboardingDone,
  setDisplayName,
  setReminderChoice,
  type ReminderChoice,
} from '@/lib/session'
import styles from './OnboardingPage.module.css'

const REMINDERS: Array<{ value: ReminderChoice; label: string }> = [
  { value: '20:00', label: '20:00' },
  { value: '21:30', label: '21:30' },
  { value: '22:30', label: '22:30' },
  { value: 'off', label: 'Не напоминать' },
]

/**
 * Promo photo_3 — «Давайте познакомимся».
 * Wires name/city/reminder/consent to existing onboarding + settings APIs.
 */
export function OnboardingPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [city, setCity] = useState('Москва')
  const [utcLabel, setUtcLabel] = useState('UTC+3')
  const [timezone, setTimezone] = useState('Europe/Moscow')
  const [reminder, setReminder] = useState<ReminderChoice>('21:30')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const canSubmit = useMemo(
    () => Boolean(name.trim() && city.trim() && consent && !pending),
    [name, city, consent, pending],
  )

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }

  async function resolveTimezoneFromCity(cityName: string) {
    const trimmed = cityName.trim()
    if (!trimmed) return
    try {
      const result = await lookupCityTimezone(trimmed)
      const data = result.timezone_data ?? result.multiple_options?.[0]
      if (data?.timezone) {
        setTimezone(data.timezone)
        setUtcLabel(data.utc_offset || guessUtcLabel(data.timezone))
        return
      }
    } catch {
      /* fall through to local map */
    }
    const guess = guessTimezoneFromCity(trimmed)
    if (guess) {
      setTimezone(guess.timezone)
      setUtcLabel(guess.utc)
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    setError(null)
    setPending(true)
    try {
      await acceptOnboardingAgreement(1)
      await acceptOnboardingAgreement(2)
      try {
        await confirmCityTimezone({ timezone, city: city.trim() })
      } catch {
        await setOnboardingTimezone(timezone)
      }
      try {
        const profileId = await fetchProfileId()
        await patchProfile(profileId, { first_name: name.trim(), timezone })
      } catch {
        /* name may still live locally if profile patch fails */
      }
      await patchReminders({ notifications_enabled: reminder !== 'off' })

      setDisplayName(name.trim())
      setReminderChoice(reminder)
      markOnboardingDone()
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить')
    } finally {
      setPending(false)
    }
  }

  return (
    <AppShell variant="bleed">
      <main className={styles.page}>
        <header className={styles.top}>
          <Link to="/register" className={styles.back}>
            ← Назад
          </Link>
          <div className={styles.progress} aria-hidden="true">
            <span className={styles.dotOn} />
            <span className={styles.dotOn} />
            <span className={styles.dotOff} />
          </div>
          <span className={styles.step}>2 из 3</span>
        </header>

        <h1 className={styles.title}>Давайте познакомимся</h1>
        <p className={styles.lead}>
          Это нужно, чтобы правильно считать дни и напоминать о записи в удобное
          время.
        </p>

        <form className={styles.form} onSubmit={(e) => void onSubmit(e)}>
          <div className={styles.card}>
            <label className={styles.field}>
              <span className={styles.label}>Как к вам обращаться</span>
              <input
                className={styles.input}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Алексей"
                autoComplete="given-name"
                required
              />
            </label>

            <label className={styles.field}>
              <span className={styles.label}>Ваш город</span>
              <div className={styles.cityRow}>
                <input
                  className={styles.input}
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  onBlur={() => void resolveTimezoneFromCity(city)}
                  placeholder="Москва"
                  autoComplete="address-level2"
                  required
                />
                <span className={styles.utc}>{utcLabel}</span>
              </div>
            </label>

            <fieldset className={styles.fieldset}>
              <legend className={styles.label}>Когда напоминать о записи</legend>
              <div className={styles.chips}>
                {REMINDERS.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={
                      reminder === item.value ? styles.chipOn : styles.chipOff
                    }
                    onClick={() => setReminder(item.value)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>

          <label className={styles.consent}>
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              Я прочитал{' '}
              <a href="#terms" onClick={(e) => e.preventDefault()}>
                условия
              </a>{' '}
              и понимаю, что дневник не заменяет помощь врача
            </span>
          </label>

          {error ? <p className={styles.error}>{error}</p> : null}

          <Button type="submit" variant="primary" disabled={!canSubmit}>
            {pending ? 'Сохраняем…' : 'Дальше — первая запись'}
          </Button>
        </form>
      </main>
    </AppShell>
  )
}

function guessUtcLabel(tz: string): string {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'shortOffset',
    }).formatToParts(new Date())
    const name = parts.find((p) => p.type === 'timeZoneName')?.value
    return name?.replace('GMT', 'UTC') || 'UTC'
  } catch {
    return 'UTC'
  }
}
