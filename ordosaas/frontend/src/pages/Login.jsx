import { Package } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import * as authApi from '../api/auth'
import Button from '../components/common/Button'
import { useAuth } from '../hooks/useAuth'

export default function Login() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  if (isAuthenticated) return <Navigate to="/dashboard" replace />

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await authApi.login(email, password, remember)
      login(res)
      navigate('/dashboard')
    } catch (err) {
      setError(err.message || 'Identifiants invalides')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink p-4">
      <div className="w-full max-w-md rounded-xl border border-white/5 bg-ink-soft p-8 shadow-2xl">
        <div className="mb-8 flex flex-col items-center gap-2">
          <div className="flex items-center gap-2 font-sans text-2xl font-semibold text-white">
            <Package className="h-7 w-7 text-accent" />
            OrdoSaaS
          </div>
          <p className="font-mono text-xs uppercase tracking-widest text-accent/80">
            Ordonnancement de production industrielle
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-400">
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input border-white/10 bg-white/5 text-white placeholder:text-gray-500"
              placeholder="vous@entreprise.com"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-400">
              Mot de passe
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input border-white/10 bg-white/5 text-white placeholder:text-gray-500"
              placeholder="••••••••"
            />
          </div>
          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 text-gray-400">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              Se souvenir de moi
            </label>
            <a href="#" className="text-accent hover:underline">
              Mot de passe oublié ?
            </a>
          </div>

          {error && (
            <div className="rounded-md bg-[#C84848]/15 px-3 py-2 text-sm text-[#E89090]">{error}</div>
          )}

          <Button type="submit" loading={loading} className="w-full">
            Se connecter
          </Button>
        </form>
      </div>
    </div>
  )
}
