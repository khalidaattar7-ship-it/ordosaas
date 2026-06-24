import clsx from 'clsx'

const COLORS = {
  default: 'text-ink-soft',
  green: 'text-[#2A7A5B]',
  orange: 'text-[#A87E2E]',
  red: 'text-[#C84848]',
  blue: 'text-accent',
}

export default function KPICard({ title, value, unit, color = 'default', icon: Icon, trend }) {
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <span className="text-sm font-medium text-gray-500">{title}</span>
        {Icon && <Icon className="h-5 w-5 text-gray-300" />}
      </div>
      <div className="flex items-baseline gap-1">
        <span className={clsx('text-3xl font-semibold', COLORS[color])}>{value}</span>
        {unit && <span className="text-sm text-gray-400">{unit}</span>}
      </div>
      {trend != null && (
        <span className={clsx('text-xs', trend >= 0 ? 'text-green-600' : 'text-red-600')}>
          {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}%
        </span>
      )}
    </div>
  )
}
