import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import {
  ApiError,
  startWebAccessClaim,
  type WebAccessClaimResponse,
  type WebAccessPlatform,
} from '@/lib/api'
import styles from './AuthForm.module.css'

const PLATFORM_LABEL: Record<WebAccessPlatform, string> = {
  telegram: 'Telegram',
  max: 'MAX',
}

export function RecoverAccessPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pendingPlatform, setPendingPlatform] = useState<WebAccessPlatform | null>(null)
  const [result, setResult] = useState<WebAccessClaimResponse | null>(null)

  async function submit(platform: WebAccessPlatform) {
    setError(null)
    setResult(null)
    const trimmed = email.trim()
    if (!trimmed) {
      setError('Укажите email, который привязан к аккаунту')
      return
    }
    setPendingPlatform(platform)
    try {
      const response = await startWebAccessClaim({ email: trimmed, platform })
      setResult(response)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить запрос')
    } finally {
      setPendingPlatform(null)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void submit('telegram')
  }

  const busy = pendingPlatform !== null
  const otherPlatforms = (result?.other_platforms ?? []).filter(
    (p): p is WebAccessPlatform => p === 'telegram' || p === 'max',
  )

  return (
    <AppShell variant="bleed">
      <main className={styles.page}>
        <Link to="/login" className={styles.back}>
          ← Ко входу
        </Link>
        <h1 className={styles.title}>Восстановить доступ</h1>
        <p className={styles.lead}>
          Почта пока не настроена. Подтвердите вход в Telegram или MAX — бот пришлёт ссылку
          задать пароль на этот же аккаунт.
        </p>

        <form className={styles.form} onSubmit={onSubmit} noValidate>
          <Field
            label="Email аккаунта"
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />

          {error ? <p className={styles.error}>{error}</p> : null}

          {result ? (
            <p className={result.delivery_ok ? styles.success : styles.notice}>{result.detail}</p>
          ) : null}

          <div className={styles.actions}>
            <Button
              type="button"
              variant="primary"
              disabled={busy}
              onClick={() => void submit('telegram')}
            >
              {pendingPlatform === 'telegram' ? 'Отправляем…' : 'Подтвердить в Telegram'}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => void submit('max')}
            >
              {pendingPlatform === 'max' ? 'Отправляем…' : 'Подтвердить в MAX'}
            </Button>
          </div>

          {result?.status === 'pending' && otherPlatforms.length > 0 ? (
            <p className={styles.hint}>
              Не пришло? Попробуйте{' '}
              {otherPlatforms.map((platform, index) => (
                <span key={platform}>
                  {index > 0 ? ' или ' : null}
                  <button
                    type="button"
                    className={styles.linkButton}
                    disabled={busy}
                    onClick={() => void submit(platform)}
                  >
                    {PLATFORM_LABEL[platform]}
                  </button>
                </span>
              ))}
              .
            </p>
          ) : null}
        </form>

        <p className={styles.meta}>
          Вспомнили пароль? <Link to="/login">Войти</Link>
        </p>
      </main>
    </AppShell>
  )
}
