import clsx from 'clsx'

const STYLES = {
  draft: 'bg-gray-100 text-gray-700',
  solved: 'bg-green-100 text-green-700',
  completed: 'bg-green-100 text-green-700',
  running: 'bg-blue-100 text-blue-700 animate-pulse',
  solving: 'bg-blue-100 text-blue-700 animate-pulse',
  pending: 'bg-yellow-100 text-yellow-700',
  partial: 'bg-amber-100 text-amber-700',
  failed: 'bg-red-100 text-red-700',
  error: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-400',
  active: 'bg-green-100 text-green-700',
  inactive: 'bg-gray-100 text-gray-400',
  maintenance: 'bg-amber-100 text-amber-700',
  admin: 'bg-purple-100 text-purple-700',
  planificateur: 'bg-blue-100 text-blue-700',
  lecteur: 'bg-gray-100 text-gray-600',
}

export default function Badge({ status, label }) {
  const cls = STYLES[status] || 'bg-gray-100 text-gray-700'
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
        cls,
      )}
    >
      {label || status}
    </span>
  )
}
