import { ZoomIn, ZoomOut } from 'lucide-react'
import { useMemo, useState } from 'react'

import GanttRow from './GanttRow'
import WindowOverlay from './WindowOverlay'

const ROW_HEIGHT = 40
const LABEL_WIDTH = 120

export default function GanttChart({ ganttData, onJobSelect }) {
  const [zoom, setZoom] = useState(3)
  const [selectedJobId, setSelectedJobId] = useState(null)

  const { machines = [], entries = [], windows = [], horizon = 0 } = ganttData || {}
  const width = Math.max(600, horizon * zoom)

  const entriesByMachine = useMemo(() => {
    const map = {}
    for (const m of machines) map[m.id] = []
    for (const e of entries) {
      if (!map[e.machine_id]) map[e.machine_id] = []
      map[e.machine_id].push(e)
    }
    return map
  }, [machines, entries])

  const ticks = useMemo(() => {
    const step = zoom >= 6 ? 10 : zoom >= 3 ? 25 : 50
    const out = []
    for (let t = 0; t <= horizon; t += step) out.push(t)
    return out
  }, [horizon, zoom])

  const handleSelect = (entry) => {
    setSelectedJobId(entry.job_id)
    onJobSelect?.(entry)
  }

  const totalHeight = machines.length * ROW_HEIGHT

  return (
    <div className="card print-full">
      <div className="no-print mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-700">Diagramme de Gantt</h3>
        <div className="flex items-center gap-2">
          <button className="btn-secondary" onClick={() => setZoom((z) => Math.max(1, z - 1))}>
            <ZoomOut className="h-4 w-4" />
          </button>
          <span className="w-16 text-center text-sm text-gray-500">{zoom}px/u</span>
          <button className="btn-secondary" onClick={() => setZoom((z) => Math.min(20, z + 1))}>
            <ZoomIn className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <div style={{ width: width + LABEL_WIDTH }}>
          {/* time axis */}
          <div className="flex border-b border-gray-200">
            <div className="shrink-0" style={{ width: LABEL_WIDTH }} />
            <div className="relative" style={{ width, height: 24 }}>
              {ticks.map((t) => (
                <div
                  key={t}
                  className="absolute top-0 text-[10px] text-gray-400"
                  style={{ left: t * zoom }}
                >
                  <div className="h-2 w-px bg-gray-300" />
                  {t}
                </div>
              ))}
            </div>
          </div>

          {/* rows with window overlay */}
          <div className="relative">
            <div className="absolute" style={{ left: LABEL_WIDTH, top: 0, width, height: totalHeight }}>
              <WindowOverlay windows={windows} zoom={zoom} height={totalHeight} />
            </div>
            {machines.map((m) => (
              <GanttRow
                key={m.id}
                machine={m}
                entries={entriesByMachine[m.id] || []}
                zoom={zoom}
                rowHeight={ROW_HEIGHT}
                width={width}
                selectedJobId={selectedJobId}
                onSelect={handleSelect}
              />
            ))}
          </div>
        </div>
      </div>

      {/* legend */}
      <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-500">
        <Legend color="#C84848" label="En retard" />
        <Legend color="#2A7A5B" label="À l'heure" />
        <Legend color="#9ca3af" label="Setup" />
        <Legend color="rgba(196,150,58,0.35)" label="Fenêtre" />
      </div>
    </div>
  )
}

function Legend({ color, label }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}
