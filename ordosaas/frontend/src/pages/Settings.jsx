import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'

import { getTenant, updateTenant } from '../api/tenant'
import Button from '../components/common/Button'
import LoadingSpinner from '../components/common/LoadingSpinner'
import { useAuth } from '../hooks/useAuth'

export default function Settings() {
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['tenant'], queryFn: getTenant })
  const [form, setForm] = useState(null)

  useEffect(() => {
    if (data) {
      setForm({
        name: data.name,
        default_wr: data.default_wr,
        default_timeout: data.default_timeout,
        default_strategy: data.default_strategy,
        timezone: data.timezone,
      })
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: updateTenant,
    onSuccess: () => {
      toast.success('Paramètres enregistrés')
      queryClient.invalidateQueries({ queryKey: ['tenant'] })
    },
    onError: (e) => toast.error(e.message),
  })

  if (isLoading || !form) return <LoadingSpinner label="Chargement des paramètres..." />

  return (
    <div className="max-w-xl space-y-5">
      <h1 className="text-2xl font-bold text-gray-800">Paramètres</h1>
      <div className="card space-y-4">
        <Field label="Nom de l'organisation">
          <input
            className="input"
            disabled={!isAdmin}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </Field>
        <Field label="WR par défaut">
          <input
            type="number"
            className="input"
            disabled={!isAdmin}
            value={form.default_wr}
            onChange={(e) => setForm({ ...form, default_wr: Number(e.target.value) })}
          />
        </Field>
        <Field label="Timeout par défaut (s)">
          <input
            type="number"
            className="input"
            disabled={!isAdmin}
            value={form.default_timeout}
            onChange={(e) => setForm({ ...form, default_timeout: Number(e.target.value) })}
          />
        </Field>
        <Field label="Stratégie par défaut">
          <select
            className="input"
            disabled={!isAdmin}
            value={form.default_strategy}
            onChange={(e) => setForm({ ...form, default_strategy: e.target.value })}
          >
            <option value="auto">auto</option>
            <option value="cpsat">cpsat</option>
            <option value="lns">lns</option>
            <option value="atcs">atcs</option>
          </select>
        </Field>
        <Field label="Fuseau horaire">
          <input
            className="input"
            disabled={!isAdmin}
            value={form.timezone}
            onChange={(e) => setForm({ ...form, timezone: e.target.value })}
          />
        </Field>
        {isAdmin && (
          <Button onClick={() => mutation.mutate(form)} loading={mutation.isPending}>
            Enregistrer
          </Button>
        )}
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  )
}
