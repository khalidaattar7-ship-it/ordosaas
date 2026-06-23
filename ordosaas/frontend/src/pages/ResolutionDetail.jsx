import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Loader2, Printer, X } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { getJobInResolution } from '../api/resolutions'
import Badge from '../components/common/Badge'
import KPICard from '../components/common/KPICard'
import LoadingSpinner from '../components/common/LoadingSpinner'
import GanttChart from '../components/gantt/GanttChart'
import { useResolution } from '../hooks/useResolution'

const PHASES = [
  { id: 1, label: 'ATCS Initial' },
  { id: 2, label: 'Fenêtres' },
  { id: 3, label: 'Optimisation' },
  { id: 4, label: 'Inter-fenêtres' },
]

function PhaseProgress({ resolution }) {
  const current = resolution.current_phase || 0
  const detail = resolution.progress_detail || {}
  return (
    <div className="card space-y-4">
      <div>
        <div className="mb-1 flex justify-between text-sm">
          <span className="font-medium text-gray-700">Progression</span>
          <span className="text-gray-500">{resolution.progress_pct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
          <div
            className="h-full bg-accent transition-all"
            style={{ width: `${resolution.progress_pct}%` }}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {PHASES.map((p) => {
          const done = current > p.id
          const active = current === p.id
          return (
            <div
              key={p.id}
              className={`flex items-center gap-2 rounded-md border p-2 text-sm ${
                active ? 'border-accent bg-blue-50' : 'border-gray-100'
              }`}
            >
              {done ? (
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              ) : active ? (
                <Loader2 className="h-4 w-4 animate-spin text-accent" />
              ) : (
                <span className="h-4 w-4 rounded-full border border-gray-300" />
              )}
              <span className={done || active ? 'text-gray-800' : 'text-gray-400'}>
                Phase {p.id} — {p.label}
              </span>
            </div>
          )
        })}
      </div>
      {detail.label && <p className="text-sm text-gray-500">{detail.label}</p>}
    </div>
  )
}

function kpiColor(twt) {
  if (twt === 0) return 'green'
  if (twt < 100) return 'orange'
  return 'red'
}

function JobPanel({ resolutionId, entry, onClose }) {
  const { data } = useQuery({
    queryKey: ['jobInResolution', resolutionId, entry?.job_id],
    queryFn: () => getJobInResolution(resolutionId, entry.job_id),
    enabled: !!entry,
  })
  if (!entry) return null
  return (
    <div className="card h-fit w-80 shrink-0">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">{entry.job_external_id}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <X className="h-4 w-4" />
        </button>
      </div>
      {!data ? (
        <LoadingSpinner />
      ) : (
        <div className="space-y-2 text-sm">
          <Row k="Deadline" v={data.deadline} />
          <Row k="Poids" v={data.weight} />
          <Row k="Completion" v={data.completion_time} />
          <Row k="Retard" v={data.tardiness} highlight={data.is_late} />
          <Row k="Retard pondéré" v={data.weighted_tardiness} />
          <div className="pt-2">
            <div className="mb-1 text-xs font-medium text-gray-500">Opérations</div>
            {data.operations.map((op, i) => (
              <div key={i} className="rounded bg-gray-50 px-2 py-1 text-xs">
                #{op.position} • {op.machine_external_id} • {op.start_time}→{op.end_time}
                {op.setup_duration > 0 && ` (setup ${op.setup_duration})`}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ k, v, highlight }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{k}</span>
      <span className={highlight ? 'font-medium text-red-600' : 'font-medium text-gray-800'}>{v}</span>
    </div>
  )
}

export default function ResolutionDetail() {
  const { id } = useParams()
  const { resolution, ganttData, isRunning, isCompleted, isLoading } = useResolution(id)
  const [selected, setSelected] = useState(null)

  if (isLoading || !resolution) return <LoadingSpinner label="Chargement de la résolution..." />

  const kpis = resolution.kpis

  return (
    <div className="space-y-5">
      <div className="no-print flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-800">Résolution</h1>
          <Badge status={resolution.status} />
          {resolution.method_used && (
            <span className="text-sm text-gray-400">méthode : {resolution.method_used}</span>
          )}
        </div>
        {isCompleted && (
          <button className="btn-secondary" onClick={() => window.print()}>
            <Printer className="h-4 w-4" /> Exporter le planning
          </button>
        )}
      </div>

      {isRunning && <PhaseProgress resolution={resolution} />}

      {resolution.status === 'failed' && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          Échec : {resolution.error_message}
        </div>
      )}

      {isCompleted && kpis && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <KPICard
            title="Retard pondéré total"
            value={kpis.total_weighted_tardiness ?? '—'}
            color={kpiColor(kpis.total_weighted_tardiness)}
          />
          <KPICard
            title="Jobs en retard"
            value={`${kpis.nb_jobs_late ?? 0}/${(kpis.nb_jobs_late ?? 0) + (kpis.nb_jobs_on_time ?? 0)}`}
          />
          <KPICard title="Utilisation machines" value={kpis.machine_utilization_pct ?? '—'} unit="%" color="blue" />
          <KPICard
            title="Amélioration vs ATCS"
            value={kpis.improvement_vs_atcs_pct ?? '—'}
            unit="%"
            color="green"
          />
          <KPICard title="Temps de résolution" value={resolution.duration_seconds ?? '—'} unit="s" />
        </div>
      )}

      {isCompleted && ganttData && (
        <div className="flex gap-4">
          <div className="min-w-0 flex-1">
            <GanttChart ganttData={ganttData} onJobSelect={setSelected} />
          </div>
          {selected && (
            <JobPanel resolutionId={id} entry={selected} onClose={() => setSelected(null)} />
          )}
        </div>
      )}
    </div>
  )
}
