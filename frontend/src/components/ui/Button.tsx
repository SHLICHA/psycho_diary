import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import styles from './Button.module.css'

type Variant = 'primary' | 'secondary'

type Common = {
  variant?: Variant
  children: ReactNode
  className?: string
}

type AsButton = Common &
  ButtonHTMLAttributes<HTMLButtonElement> & {
    to?: undefined
  }

type AsLink = Common & {
  to: string
  type?: never
  disabled?: boolean
  onClick?: never
}

export type ButtonProps = AsButton | AsLink

export function Button({
  variant = 'primary',
  className,
  children,
  ...rest
}: ButtonProps) {
  const classes = [styles.btn, styles[variant], className]
    .filter(Boolean)
    .join(' ')

  if ('to' in rest && rest.to) {
    const { to, disabled, ...linkRest } = rest
    if (disabled) {
      return (
        <span className={`${classes} ${styles.disabled}`} aria-disabled="true">
          {children}
        </span>
      )
    }
    return (
      <Link to={to} className={classes} {...linkRest}>
        {children}
      </Link>
    )
  }

  const buttonRest = rest as AsButton
  return (
    <button type={buttonRest.type ?? 'button'} className={classes} {...buttonRest}>
      {children}
    </button>
  )
}
