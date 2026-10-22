import { AppShell } from '@/components/AppShell'
import { EveningDeskIllustration } from '@/components/EveningDeskIllustration'
import { Button } from '@/components/ui/Button'
import styles from './WelcomePage.module.css'

/**
 * Promo photo_4 composition: one vertical story on a full-bleed night stage.
 * Desktop scales the same composition — no broken mock-JPG split.
 */
export function WelcomePage() {
  return (
    <AppShell variant="stage">
      <main className={styles.page}>
        <div className={styles.stage}>
          <EveningDeskIllustration />

          <div className={styles.copy}>
            <p className={styles.eyebrow}>Дневник с ИИ-психологом</p>
            <h1 className={styles.title}>Psycho Diary</h1>
            <p className={styles.lead}>
              Тихое место в конце дня: записать, что было, и спокойно разобраться
              в себе.
            </p>
          </div>

          <div className={styles.actions}>
            <Button to="/register" variant="primary">
              Начать дневник
            </Button>
            <Button to="/login" variant="secondary">
              Войти
            </Button>
          </div>

          <p className={styles.privacy}>
            <LockIcon />
            <span>Записи шифруются и видны только вам</span>
          </p>
        </div>
      </main>
    </AppShell>
  )
}

function LockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect
        x="5"
        y="11"
        width="14"
        height="10"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M8 11V8a4 4 0 0 1 8 0v3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}
