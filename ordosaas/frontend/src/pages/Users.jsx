import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'

import { deleteUser, inviteUser, listUsers, patchUser } from '../api/tenant'
import Badge from '../components/common/Badge'
import Button from '../components/common/Button'
import Modal from '../components/common/Modal'
import Table from '../components/common/Table'

export default function Users() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [invite, setInvite] = useState({ email: '', role: 'lecteur' })

  const { data, isLoading } = useQuery({
    queryKey: ['users', page],
    queryFn: () => listUsers({ page, per_page: 20 }),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['users'] })

  const inviteMut = useMutation({
    mutationFn: () => inviteUser(invite.email, invite.role),
    onSuccess: () => {
      toast.success('Invitation envoyée')
      setOpen(false)
      setInvite({ email: '', role: 'lecteur' })
      invalidate()
    },
    onError: (e) => toast.error(e.message),
  })
  const patchMut = useMutation({
    mutationFn: ({ id, body }) => patchUser(id, body),
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  })
  const deleteMut = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      toast.success('Utilisateur supprimé')
      invalidate()
    },
    onError: (e) => toast.error(e.message),
  })

  const columns = [
    { key: 'email', label: 'Email', render: (r) => <span className="font-medium">{r.email}</span> },
    { key: 'name', label: 'Nom', render: (r) => `${r.first_name} ${r.last_name}`.trim() || '—' },
    {
      key: 'role',
      label: 'Rôle',
      render: (r) => (
        <select
          className="rounded border border-gray-200 px-2 py-1 text-xs"
          value={r.role}
          onChange={(e) => patchMut.mutate({ id: r.id, body: { role: e.target.value } })}
        >
          <option value="admin">admin</option>
          <option value="planificateur">planificateur</option>
          <option value="lecteur">lecteur</option>
        </select>
      ),
    },
    { key: 'status', label: 'Statut', render: (r) => <Badge status={r.status} /> },
    {
      key: 'actions',
      label: 'Actions',
      render: (r) => (
        <div className="flex items-center gap-2">
          <button
            className="text-xs text-gray-500 hover:text-accent"
            onClick={() =>
              patchMut.mutate({
                id: r.id,
                body: { status: r.status === 'active' ? 'inactive' : 'active' },
              })
            }
          >
            {r.status === 'active' ? 'Désactiver' : 'Activer'}
          </button>
          <button
            className="text-gray-500 hover:text-red-600"
            onClick={() => {
              if (confirm(`Supprimer ${r.email} ?`)) deleteMut.mutate(r.id)
            }}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Utilisateurs</h1>
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Inviter un utilisateur
        </Button>
      </div>

      <Table
        columns={columns}
        data={data?.data}
        loading={isLoading}
        pagination={data?.pagination}
        onPageChange={setPage}
        emptyLabel="Aucun utilisateur"
      />

      <Modal open={open} onClose={() => setOpen(false)} title="Inviter un utilisateur">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            inviteMut.mutate()
          }}
        >
          <div>
            <label className="mb-1 block text-sm text-gray-600">Email</label>
            <input
              type="email"
              className="input"
              required
              value={invite.email}
              onChange={(e) => setInvite({ ...invite, email: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-gray-600">Rôle</label>
            <select
              className="input"
              value={invite.role}
              onChange={(e) => setInvite({ ...invite, role: e.target.value })}
            >
              <option value="lecteur">lecteur</option>
              <option value="planificateur">planificateur</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <Button type="submit" loading={inviteMut.isPending} className="w-full">
            Inviter
          </Button>
        </form>
      </Modal>
    </div>
  )
}
