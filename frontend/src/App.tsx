import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { DiaryHomePage } from '@/pages/DiaryHomePage'
import { LoginPage } from '@/pages/LoginPage'
import { OnboardingPage } from '@/pages/OnboardingPage'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import { RecoverAccessPage } from '@/pages/RecoverAccessPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { SetPasswordPage } from '@/pages/SetPasswordPage'
import { WelcomePage } from '@/pages/WelcomePage'
import { isAuthenticated } from '@/lib/authStorage'
import { isOnboardingDone } from '@/lib/session'

function GuestOnly({ children }: { children: ReactNode }) {
  if (isAuthenticated()) {
    return <Navigate to={isOnboardingDone() ? '/app' : '/onboarding'} replace />
  }
  return children
}

function RequireAuth({ children }: { children: ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <GuestOnly>
            <WelcomePage />
          </GuestOnly>
        }
      />
      <Route
        path="/login"
        element={
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        }
      />
      <Route
        path="/register"
        element={
          <GuestOnly>
            <RegisterPage />
          </GuestOnly>
        }
      />
      <Route
        path="/recover"
        element={
          <GuestOnly>
            <RecoverAccessPage />
          </GuestOnly>
        }
      />
      <Route
        path="/auth/set-password/:token/"
        element={
          <GuestOnly>
            <SetPasswordPage />
          </GuestOnly>
        }
      />
      <Route
        path="/auth/set-password/:token"
        element={
          <GuestOnly>
            <SetPasswordPage />
          </GuestOnly>
        }
      />
      <Route
        path="/onboarding"
        element={
          <RequireAuth>
            <OnboardingPage />
          </RequireAuth>
        }
      />
      <Route path="/app" element={<DiaryHomePage />} />
      <Route
        path="/archive"
        element={
          <PlaceholderPage title="Архив" note="Календарь и список дней — следующий этап." />
        }
      />
      <Route
        path="/progress"
        element={
          <PlaceholderPage title="Прогресс" note="Стрик, график и отчёты появятся здесь." />
        }
      />
      <Route
        path="/profile"
        element={
          <PlaceholderPage title="Профиль" note="Портрет и настройки подключим после дневника." />
        }
      />
      <Route
        path="/entries/new"
        element={
          <PlaceholderPage
            title="Новая запись"
            note="Экран тетради и анализа — следующий шаг P0."
            showNav={false}
          />
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
