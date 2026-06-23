import clsx from 'clsx'

export default function LoadingSpinner({ className, label }) {
  return (
    <div className={clsx('flex items-center justify-center gap-3 py-8 text-gray-500', className)}>
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}
