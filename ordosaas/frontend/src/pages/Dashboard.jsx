import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { CheckCircle2, Package, Timer, TrendingUp } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { listInstances } from '../api/instances'
import Badge from '../components/common/Badge'
import KPICard from '../components/common/KPICard'
import LoadingSpinner from '../components/common/LoadingSpinner'
import Table from '../components/common/Table'

export default function Dashboard() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['instances', { page: 1, per_page: 100 }],
    queryFn: () => listInstances({ page: 1, per_page: 100 }),
    staleTime: 30_000,
  })

  if (isLoading) return <LoadingSpinner label="Chargement du tableau de bord..." />

  const instances = data?.data || []
  const solved = instances.filter((i) => i.status === 'solved')
  const totalResolutions = instances.reduce((acc, i) => acc + (i.nb_resolutions || 0), 0)
  const bestTwts = solved
    .map((i) => i.best_weighted_tardiness)
    .filter((v) => v != null)
  const avgTwt = bestTwts.length
    ? (bestTwts.reduce((a, b) => a + b, 0) / bestTwts.length).toFixed(1)
    : '—'

  const recent = [...instances]
    .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
    .slice(0, 5)

  const columns = [
    { key: 'name', label: 'Instance', render: (r) => <span className="font-medium">{r.name}</span> },
    { key: 'nb_jobs', label: 'Jobs' },
    { key: 'nb_machines', label: 'Machines' },
    { key: 'status', label: 'Status', render: (r) => <Badge status={r.status} /> },
    {
      key: 'best_weighted_tardiness',
      label: 'Best TWT',
      render: (r) => (r.best_weighted_tardiness != null ? r.best_weighted_tardiness : '—'),
    },
    {
      key: 'created_at',
      label: 'Date',
      render: (r) => format(new Date(r.updated_at), 'dd/MM/yyyy HH:mm'),
    },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Tableau de bord</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard title="Total instances" value={instances.length} icon={Package} />
        <KPICard title="Instances résolues" value={solved.length} color="green" icon={CheckCircle2} />
        <KPICard title="Total résolutions" value={totalResolutions} color="blue" icon={Timer} />
        <KPICard title="TWT moyen (best)" value={avgTwt} color="orange" icon={TrendingUp} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-700">Dernières instances</h2>
        <Table
          columns={[
            ...columns,
            {
              key: 'open',
              label: '',
              render: (r) => (
                <button
                  className="text-sm text-accent hover:underline"
                  onClick={() => navigate(`/instances/${r.id}`)}
                >
                  Ouvrir
                </button>
              ),
            },
          ]}
          data={recent}
          emptyLabel="Aucune instance pour le moment"
        />
      </div>
    </div>
  )
}
