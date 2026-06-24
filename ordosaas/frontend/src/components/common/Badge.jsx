import clsx from 'clsx'

// Status palette aligned with the .dc.html mockups:
// success #2A7A5B, danger #C84848, brass #C4963A, ink/muted neutrals.
const SUCCESS = 'bg-[#2A7A5B]/12 text-[#2A7A5B]'
const DANGER = 'bg-[#C84848]/12 text-[#C84848]'
const GOLD = 'bg-[#C4963A]/15 text-[#A87E2E]'
const NEUTRAL = 'bg-[#ECEAE4] text-[#666677]'
const FADED = 'bg-[#F2F1EE] text-[#AAAAB8]'

const STYLES = {
  draft: NEUTRAL,
  solved: SUCCESS,
  completed: SUCCESS,
  running: `${GOLD} animate-pulse`,
  solving: `${GOLD} animate-pulse`,
  pending: GOLD,
  partial: GOLD,
  failed: DANGER,
  error: DANGER,
  cancelled: FADED,
  active: SUCCESS,
  inactive: FADED,
  maintenance: GOLD,
  admin: GOLD,
  planificateur: 'bg-[#3A5A8A]/12 text-[#3A5A8A]',
  lecteur: NEUTRAL,
}

export default function Badge({ status, label }) {
  const cls = STYLES[status] || NEUTRAL
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
