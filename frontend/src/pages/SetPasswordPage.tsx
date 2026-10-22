import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { ApiError, fetchOnboardingStatus, setWebAccessPassword } from '@/lib/api'
import { isOnboardingDone, markOnboardingDone } from '@/lib/session'
import styles from './AuthForm.module.css'

export function SetPasswordPage() {
  const { token = '' } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (!token) {
      setError('Ссылка неполная. Запросите доступ снова.')
      return
    }
    if (password !== passwordConfirm) {
      setError('Пароли не совпадают')
      return
    }
    if (password.length < 8) {
      setError('Пароль не короче 8 символов')
      return
    }
    setPending(true)
    try {
      await setWebAccessPassword({ token, password, passwordConfirm })
      try {
        const status = await fetchOnboardingStatus()
        if (status.mode && !['agreement', 'agreement_2', 'timezone'].includes(status.mode)) {
          markOnboardingDone()
        }
      } catch {
        /* keep local flag */
      }
      navigate(isOnboardingDone() ? '/app' : '/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить пароль')
    } finally {
      setPending(false)
    }
  }

  return (
    <AppShell variant="bleed">
      <main className={styles.page}>
        <Link to="/recover" className={styles.back}>
          ← Восстановить доступ
        </Link>
        <h1 className={styles.title}>Задать пароль</h1>
        <p className={styles.lead}>После сохранения войдёте в дневник на этом устройстве</p>

        <form className={styles.form} onSubmit={onSubmit} noValidate>
          <Field
            label="Новый пароль"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="не короче 8, не слишком простой"
          />
          <Field
            label="Повторите пароль"
            name="password_confirm"
            type="password"
            autoComplete="new-password"
            required
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            placeholder="ещё раз"
          />

          {error ? <p className={styles.error}>{error}</p> : null}

          <Button type="submit" variant="primary" disabled={pending || !token}>
            {pending ? 'Сохраняем…' : 'Сохранить и войти'}
          </Button>
        </form>
      </main>
    </AppShell>
  )
}
