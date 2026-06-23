import { useAuthStore } from '../stores/authStore'

export function useAuth() {
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const login = useAuthStore((s) => s.login)
  const logout = useAuthStore((s) => s.logout)
  return {
    user,
    isAuthenticated,
    login,
    logout,
    isAdmin: user?.role === 'admin',
    isPlanner: ['admin', 'planificateur'].includes(user?.role),
  }
}
