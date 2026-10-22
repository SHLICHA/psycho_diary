import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { ApiError, fetchOnboardingStatus, loginAccount } from '@/lib/api'
import { isOnboardingDone, markOnboardingDone } from '@/lib/session'
import styles from './AuthForm.module.css'

export function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      await loginAccount({ email: email.trim(), password })
      try {
        const status = await fetchOnboardingStatus()
        // Backend modes after completed onboarding typically leave agreement/timezone behind.
        if (status.mode && !['agreement', 'agreement_2', 'timezone'].includes(status.mode)) {
          markOnboardingDone()
        }
      } catch {
        /* keep local onboarding flag */
      }
      navigate(isOnboardingDone() ? '/app' : '/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось войти')
    } finally {
      setPending(false)
    }
  }

  return (
    <AppShell variant="bleed">
      <main className={styles.page}>
        <Link to="/" className={styles.back}>
          ← Назад
        </Link>
        <h1 className={styles.title}>Вход</h1>
        <p className={styles.lead}>Войдите по email и паролю</p>

        <form className={styles.form} onSubmit={onSubmit} noValidate>
          <Field
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <Field
            label="Пароль"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />

          {error ? <p className={styles.error}>{error}</p> : null}

          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? 'Входим…' : 'Войти'}
          </Button>
        </form>

        <p className={styles.meta}>
          Нет пароля или забыли? <Link to="/recover">Восстановить через бота</Link>
        </p>
        <p className={styles.meta}>
          Нет аккаунта? <Link to="/register">Создать</Link>
        </p>
      </main>
    </AppShell>
  )
}
