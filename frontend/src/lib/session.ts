const ONBOARDING_KEY = 'pd.onboarding_done'
const DISPLAY_NAME_KEY = 'pd.display_name'
const REMINDER_KEY = 'pd.reminder'

export type ReminderChoice = '20:00' | '21:30' | '22:30' | 'off'

export function isOnboardingDone(): boolean {
  return localStorage.getItem(ONBOARDING_KEY) === '1'
}

export function markOnboardingDone(): void {
  localStorage.setItem(ONBOARDING_KEY, '1')
}

export function clearSessionMeta(): void {
  localStorage.removeItem(ONBOARDING_KEY)
  localStorage.removeItem(DISPLAY_NAME_KEY)
  localStorage.removeItem(REMINDER_KEY)
}

export function setDisplayName(name: string): void {
  localStorage.setItem(DISPLAY_NAME_KEY, name.trim())
}

export function getDisplayName(): string {
  return localStorage.getItem(DISPLAY_NAME_KEY) || ''
}

export function setReminderChoice(value: ReminderChoice): void {
  localStorage.setItem(REMINDER_KEY, value)
}

export function getReminderChoice(): ReminderChoice {
  const v = localStorage.getItem(REMINDER_KEY)
  if (v === '20:00' || v === '21:30' || v === '22:30' || v === 'off') return v
  return '21:30'
}
