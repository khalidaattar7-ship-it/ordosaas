import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { Eye, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'

import { deleteInstance, listInstances } from '../api/instances'
import Badge from '../components/common/Badge'
import Button from '../components/common/Button'
import Modal from '../components/common/Modal'
import Table from '../components/common/Table'
import ImportForm from '../components/forms/ImportForm'

export default function Instances() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [importOpen, setImportOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['instances', { page, search }],
    queryFn: () => listInstances({ page, per_page: 20, search: search || undefined }),
  })

  const delMutation = useMutation({
    mutationFn: deleteInstance,
    onSuccess: () => {
      toast.success('Instance supprimée')
      queryClient.invalidateQueries({ queryKey: ['instances'] })
    },
    onError: (e) => toast.error(e.message),
  })

  const columns = [
    { key: 'name', label: 'Nom', render: (r) => <span className="font-medium">{r.name}</span> },
    { key: 'nb_jobs', label: 'Jobs' },
    { key: 'nb_machines', label: 'Machines' },
    { key: 'status', label: 'Status', render: (r) => <Badge status={r.status} /> },
    { key: 'nb_resolutions', label: 'Résolutions' },
    {
      key: 'best_weighted_tardiness',
      label: 'Best TWT',
      render: (r) => (r.best_weighted_tardiness != null ? r.best_weighted_tardiness : '—'),
    },
    {
      key: 'created_at',
      label: 'Créé le',
      render: (r) => format(new Date(r.created_at), 'dd/MM/yyyy'),
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (r) => (
        <div className="flex gap-2">
          <button
            className="text-gray-500 hover:text-accent"
            onClick={() => navigate(`/instances/${r.id}`)}
            title="Voir"
          >
            <Eye className="h-4 w-4" />
          </button>
          <button
            className="text-gray-500 hover:text-red-600"
            onClick={() => {
              if (confirm(`Supprimer l'instance "${r.name}" ?`)) delMutation.mutate(r.id)
            }}
            title="Supprimer"
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
        <h1 className="text-2xl font-bold text-gray-800">Instances</h1>
        <Button onClick={() => setImportOpen(true)}>
          <Plus className="h-4 w-4" /> Importer une instance
        </Button>
      </div>

      <input
        className="input max-w-xs"
        placeholder="Rechercher..."
        value={search}
        onChange={(e) => {
          setPage(1)
          setSearch(e.target.value)
        }}
      />

      <Table
        columns={columns}
        data={data?.data}
        loading={isLoading}
        pagination={data?.pagination}
        onPageChange={setPage}
        emptyLabel="Aucune instance"
      />

      <Modal open={importOpen} onClose={() => setImportOpen(false)} title="Importer une instance">
        <ImportForm
          onSuccess={() => {
            setImportOpen(false)
            queryClient.invalidateQueries({ queryKey: ['instances'] })
            toast.success('Instance importée')
          }}
        />
      </Modal>
    </div>
  )
}
