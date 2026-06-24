import clsx from 'clsx'
import {
  GitCompareArrows,
  LayoutDashboard,
  Package,
  ScrollText,
  Settings,
  Settings2,
  Users,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { useAuth } from '../../hooks/useAuth'

const LINKS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/instances', label: 'Instances', icon: Package },
  { to: '/comparisons', label: 'Comparaisons', icon: GitCompareArrows },
  { to: '/machines', label: 'Machines', icon: Settings2 },
  { to: '/users', label: 'Utilisateurs', icon: Users, admin: true },
  { to: '/audit', label: 'Audit Logs', icon: ScrollText, admin: true },
  { to: '/settings', label: 'Paramètres', icon: Settings },
]

export default function Sidebar() {
  const { isAdmin } = useAuth()
  return (
    <aside className="flex h-screen w-60 flex-col bg-sidebar text-gray-300">
      <div className="flex h-16 items-center gap-2 px-5 text-xl font-bold text-white">
        <Package className="h-6 w-6 text-accent" />
        OrdoSaaS
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {LINKS.filter((l) => !l.admin || isAdmin).map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive ? 'bg-accent text-ink font-semibold' : 'text-gray-400 hover:bg-white/5 hover:text-white',
              )
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-3 text-xs text-gray-500">OrdoSaaS v1.0</div>
    </aside>
  )
}
