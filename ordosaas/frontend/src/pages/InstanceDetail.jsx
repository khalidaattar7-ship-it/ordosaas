import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Play } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { useNavigate, useParams } from 'react-router-dom'

import {
  getInstance,
  listJobs,
  patchJob,
  resolveInstance,
} from '../api/instances'
import Badge from '../components/common/Badge'
import Button from '../components/common/Button'
import Modal from '../components/common/Modal'
import Table from '../components/common/Table'
import SolverConfigForm from '../components/forms/SolverConfigForm'

function JobsTab({ instanceId }) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState(null)
  const { data, isLoading } = useQuery({
    queryKey: ['jobs', instanceId, page],
    queryFn: () => listJobs(instanceId, { page, per_page: 50 }),
  })

  const patchMutation = useMutation({
    mutationFn: ({ jobId, body }) => patchJob(instanceId, jobId, body),
    onSuccess: () => {
      toast.success('Job mis à jour')
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ['jobs', instanceId] })
    },
    onError: (e) => toast.error(e.message),
  })

  const columns = [
    { key: 'external_id', label: 'Job ID', render: (r) => <span className="font-medium">{r.external_id}</span> },
    { key: 'deadline', label: 'Deadline' },
    { key: 'weight', label: 'Poids' },
    { key: 'nb_operations', label: 'Opérations' },
    { key: 'machines', label: 'Machines', render: (r) => (r.machines || []).join(', ') },
    {
      key: 'actions',
      label: 'Actions',
      render: (r) => (
        <button className="text-gray-500 hover:text-accent" onClick={() => setEditing(r)}>
          <Pencil className="h-4 w-4" />
        </button>
      ),
    },
  ]

  return (
    <>
      <Table
        columns={columns}
        data={data?.data}
        loading={isLoading}
        pagination={data?.pagination}
        onPageChange={setPage}
      />
      <Modal open={!!editing} onClose={() => setEditing(null)} title={`Modifier ${editing?.external_id}`}>
        {editing && (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              patchMutation.mutate({
                jobId: editing.id,
                body: { deadline: Number(editing.deadline), weight: Number(editing.weight) },
              })
            }}
          >
            <div>
              <label className="mb-1 block text-sm text-gray-600">Deadline</label>
              <input
                type="number"
                className="input"
                value={editing.deadline}
                onChange={(e) => setEditing({ ...editing, deadline: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-gray-600">Poids</label>
              <input
                type="number"
                step="0.1"
                className="input"
                value={editing.weight}
                onChange={(e) => setEditing({ ...editing, weight: e.target.value })}
              />
            </div>
            <Button type="submit" loading={patchMutation.isPending} className="w-full">
              Enregistrer
            </Button>
          </form>
        )}
      </Modal>
    </>
  )
}

function ResolutionsTab({ instance }) {
  const navigate = useNavigate()
  // The instance summary carries best resolution info; full list would need a
  // dedicated endpoint, so we surface the best one and link to the Gantt.
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-500">Résolutions de cette instance</span>
        <span className="text-sm font-medium">{instance.nb_resolutions} au total</span>
      </div>
      {instance.best_resolution_id ? (
        <div className="flex items-center justify-between rounded-md border border-gray-100 p-3">
          <div>
            <div className="text-sm font-medium">Meilleure solution</div>
            <div className="text-xs text-gray-500">
              TWT = {instance.best_weighted_tardiness}
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={() => navigate(`/resolutions/${instance.best_resolution_id}`)}
          >
            Voir le Gantt
          </Button>
        </div>
      ) : (
        <p className="text-sm text-gray-400">Aucune résolution complétée.</p>
      )}
    </div>
  )
}

export default function InstanceDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState('jobs')
  const [resolveOpen, setResolveOpen] = useState(false)

  const { data: instance, isLoading } = useQuery({
    queryKey: ['instance', id],
    queryFn: () => getInstance(id),
  })

  const resolveMutation = useMutation({
    mutationFn: (config) => resolveInstance(id, config),
    onSuccess: (res) => {
      setResolveOpen(false)
      toast.success('Résolution lancée')
      navigate(`/resolutions/${res.resolution_id}`)
    },
    onError: (e) => toast.error(e.message),
  })

  if (isLoading || !instance) return <div className="p-6 text-gray-400">Chargement...</div>

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-800">{instance.name}</h1>
          <Badge status={instance.status} />
        </div>
        <Button onClick={() => setResolveOpen(true)}>
          <Play className="h-4 w-4" /> Lancer une résolution
        </Button>
      </div>

      <div className="flex gap-4 border-b border-gray-200">
        {['jobs', 'resolutions'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-1 pb-2 text-sm font-medium ${
              tab === t ? 'border-accent text-accent' : 'border-transparent text-gray-500'
            }`}
          >
            {t === 'jobs' ? 'Jobs' : 'Résolutions'}
          </button>
        ))}
      </div>

      {tab === 'jobs' ? <JobsTab instanceId={id} /> : <ResolutionsTab instance={instance} />}

      <Modal open={resolveOpen} onClose={() => setResolveOpen(false)} title="Configuration du solveur">
        <SolverConfigForm onSubmit={resolveMutation.mutate} loading={resolveMutation.isPending} />
      </Modal>
    </div>
  )
}
