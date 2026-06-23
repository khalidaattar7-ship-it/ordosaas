import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'

import { createMachine, deleteMachine, listMachines, updateMachine } from '../api/machines'
import Badge from '../components/common/Badge'
import Button from '../components/common/Button'
import Modal from '../components/common/Modal'
import Table from '../components/common/Table'
import { useAuth } from '../hooks/useAuth'

export default function Machines() {
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ external_id: '', name: '', description: '' })

  const { data, isLoading } = useQuery({ queryKey: ['machines'], queryFn: listMachines })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['machines'] })

  const createMut = useMutation({
    mutationFn: createMachine,
    onSuccess: () => {
      toast.success('Machine créée')
      setOpen(false)
      setForm({ external_id: '', name: '', description: '' })
      invalidate()
    },
    onError: (e) => toast.error(e.message),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, body }) => updateMachine(id, body),
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  })
  const deleteMut = useMutation({
    mutationFn: deleteMachine,
    onSuccess: () => {
      toast.success('Machine supprimée')
      invalidate()
    },
    onError: (e) => toast.error(e.message),
  })

  const columns = [
    { key: 'external_id', label: 'ID', render: (r) => <span className="font-medium">{r.external_id}</span> },
    { key: 'name', label: 'Nom' },
    { key: 'description', label: 'Description', render: (r) => r.description || '—' },
    {
      key: 'status',
      label: 'Statut',
      render: (r) =>
        isAdmin ? (
          <select
            className="rounded border border-gray-200 px-2 py-1 text-xs"
            value={r.status}
            onChange={(e) => updateMut.mutate({ id: r.id, body: { status: e.target.value } })}
          >
            <option value="active">active</option>
            <option value="maintenance">maintenance</option>
            <option value="inactive">inactive</option>
          </select>
        ) : (
          <Badge status={r.status} />
        ),
    },
    ...(isAdmin
      ? [
          {
            key: 'actions',
            label: 'Actions',
            render: (r) => (
              <button
                className="text-gray-500 hover:text-red-600"
                onClick={() => {
                  if (confirm(`Supprimer ${r.external_id} ?`)) deleteMut.mutate(r.id)
                }}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            ),
          },
        ]
      : []),
  ]

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Machines</h1>
        {isAdmin && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> Ajouter une machine
          </Button>
        )}
      </div>

      <Table columns={columns} data={data?.data} loading={isLoading} emptyLabel="Aucune machine" />

      <Modal open={open} onClose={() => setOpen(false)} title="Nouvelle machine">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            createMut.mutate(form)
          }}
        >
          <div>
            <label className="mb-1 block text-sm text-gray-600">External ID</label>
            <input
              className="input"
              required
              value={form.external_id}
              onChange={(e) => setForm({ ...form, external_id: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-gray-600">Nom</label>
            <input
              className="input"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-gray-600">Description</label>
            <input
              className="input"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <Button type="submit" loading={createMut.isPending} className="w-full">
            Créer
          </Button>
        </form>
      </Modal>
    </div>
  )
}
