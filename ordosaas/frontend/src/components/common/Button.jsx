import clsx from 'clsx'

const VARIANTS = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  danger: 'btn-danger',
}

export default function Button({
  variant = 'primary',
  className,
  loading = false,
  disabled,
  children,
  ...props
}) {
  return (
    <button
      className={clsx(VARIANTS[variant], className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
      )}
      {children}
    </button>
  )
}
