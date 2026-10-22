import type { InputHTMLAttributes } from 'react'
import styles from './Field.module.css'

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string
}

export function Field({ label, error, id, className, ...rest }: FieldProps) {
  const fieldId = id ?? rest.name
  return (
    <label className={[styles.field, className].filter(Boolean).join(' ')} htmlFor={fieldId}>
      <span className={styles.label}>{label}</span>
      <input id={fieldId} className={styles.input} {...rest} />
      {error ? <span className={styles.error}>{error}</span> : null}
    </label>
  )
}
