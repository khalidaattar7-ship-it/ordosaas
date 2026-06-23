import { LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import * as authApi from '../../api/auth'
import { useAuth } from '../../hooks/useAuth'
import Badge from '../common/Badge'

export default function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    try {
      await authApi.logout()
    } catch {
      /* ignore */
    }
    logout()
    navigate('/login')
  }

  return (
    <header className="no-print flex h-16 items-center justify-between border-b border-gray-100 bg-white px-6">
      <div />
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="text-sm font-medium text-gray-800">
            {user ? `${user.first_name} ${user.last_name}`.trim() || user.email : ''}
          </div>
          <div className="text-xs text-gray-400">{user?.email}</div>
        </div>
        {user?.role && <Badge status={user.role} />}
        <button
          onClick={handleLogout}
          className="flex items-center gap-1 text-sm text-gray-500 hover:text-red-600"
        >
          <LogOut className="h-4 w-4" />
          Déconnexion
        </button>
      </div>
    </header>
  )
}
