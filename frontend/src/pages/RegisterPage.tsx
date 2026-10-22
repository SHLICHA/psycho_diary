import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { ApiError, registerAccount } from '@/lib/api'
import styles from './AuthForm.module.css'

export function RegisterPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
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
      await registerAccount({
        email: email.trim(),
        password,
        passwordConfirm,
      })
      navigate('/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось зарегистрироваться')
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
        <h1 className={styles.title}>Регистрация</h1>
        <p className={styles.lead}>Создайте дневник с email и паролем</p>

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

          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? 'Создаём…' : 'Начать дневник'}
          </Button>
        </form>

        <p className={styles.meta}>
          Уже есть аккаунт? <Link to="/login">Войти</Link>
          {' · '}
          <Link to="/recover">Задать пароль через бота</Link>
        </p>
      </main>
    </AppShell>
  )
}
