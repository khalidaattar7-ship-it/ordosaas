import { useMutation } from '@tanstack/react-query'
import { GitCompareArrows } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'

import { createComparison } from '../api/comparisons'
import Badge from '../components/common/Badge'
import Button from '../components/common/Button'
import KPICard from '../components/common/KPICard'
import Table from '../components/common/Table'

export default function Comparisons() {
  const [a, setA] = useState('')
  const [b, setB] = useState('')

  const mutation = useMutation({
    mutationFn: () => createComparison(a.trim(), b.trim()),
    onError: (e) => toast.error(e.message),
  })
  const result = mutation.data

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-ink-soft">Comparer deux résolutions</h1>

      <div className="card space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
              Résolution A (UUID)
            </label>
            <input className="input" value={a} onChange={(e) => setA(e.target.value)} placeholder="uuid-a" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
              Résolution B (UUID)
            </label>
            <input className="input" value={b} onChange={(e) => setB(e.target.value)} placeholder="uuid-b" />
          </div>
        </div>
        <Button onClick={() => mutation.mutate()} loading={mutation.isPending} disabled={!a || !b}>
          <GitCompareArrows className="h-4 w-4" /> Comparer
        </Button>
      </div>

      {result && (
        <div className="space-y-5">
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted">Gagnant</span>
            <Badge status="solved" label={`Résolution ${result.winner}`} />
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KPICard
              title="Δ Retard pondéré"
              value={result.delta?.delta_weighted_tardiness ?? '—'}
              color={
                (result.delta?.delta_weighted_tardiness ?? 0) < 0 ? 'green' : 'red'
              }
            />
            <KPICard title="Δ Jobs en retard" value={result.delta?.delta_jobs_late ?? '—'} />
            <KPICard
              title="Δ Utilisation"
              value={result.delta?.delta_machine_utilization ?? '—'}
              unit="%"
            />
            <KPICard title="Δ Temps setup" value={result.delta?.delta_setup_time ?? '—'} />
          </div>

          <div>
            <h2 className="mb-3 text-lg font-semibold text-ink-soft">Jobs modifiés</h2>
            <Table
              columns={[
                { key: 'external_id', label: 'Job', render: (r) => <span className="font-medium">{r.external_id}</span> },
                { key: 'tardiness_a', label: 'Retard A', render: (r) => r.tardiness_a ?? '—' },
                { key: 'tardiness_b', label: 'Retard B', render: (r) => r.tardiness_b ?? '—' },
                {
                  key: 'delta',
                  label: 'Δ',
                  render: (r) => (
                    <span className={r.delta < 0 ? 'text-[#2A7A5B]' : 'text-[#C84848]'}>{r.delta}</span>
                  ),
                },
              ]}
              data={result.changed_jobs}
              emptyLabel="Aucune différence par job"
            />
          </div>
        </div>
      )}
    </div>
  )
}
