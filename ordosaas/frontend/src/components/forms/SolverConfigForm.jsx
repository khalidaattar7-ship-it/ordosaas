import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import Button from '../common/Button'

const DEFAULTS = {
  wr: 5,
  strategy: 'auto',
  cpsat_timeout: 30,
  max_jobs_per_window: 50,
  min_jobs_per_window: 5,
  max_recursion_depth: 4,
  max_iterations: 5,
  epsilon: 0.01,
  junction_radius: 10,
  k1: '',
  k2: '',
}

export default function SolverConfigForm({ onSubmit, loading }) {
  const [cfg, setCfg] = useState(DEFAULTS)
  const [advanced, setAdvanced] = useState(false)

  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }))

  const submit = () => {
    const payload = { ...cfg }
    payload.k1 = cfg.k1 === '' ? null : Number(cfg.k1)
    payload.k2 = cfg.k2 === '' ? null : Number(cfg.k2)
    onSubmit(payload)
  }

  const Num = ({ label, k, step = 1 }) => (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-600">{label}</label>
      <input
        type="number"
        step={step}
        className="input"
        value={cfg[k]}
        onChange={(e) => set(k, e.target.value === '' ? '' : Number(e.target.value))}
      />
    </div>
  )

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          WR (techniciens setup) : {cfg.wr}
        </label>
        <input
          type="range"
          min="1"
          max="20"
          value={cfg.wr}
          onChange={(e) => set('wr', Number(e.target.value))}
          className="w-full"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">Stratégie</label>
        <select className="input" value={cfg.strategy} onChange={(e) => set('strategy', e.target.value)}>
          <option value="auto">Auto</option>
          <option value="cpsat">CP-SAT</option>
          <option value="lns">LNS récursif</option>
          <option value="atcs">ATCS</option>
        </select>
      </div>

      <Num label="Timeout CP-SAT (s)" k="cpsat_timeout" />

      <button
        type="button"
        className="flex items-center gap-1 text-sm font-medium text-accent"
        onClick={() => setAdvanced((a) => !a)}
      >
        {advanced ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        Paramètres avancés
      </button>

      {advanced && (
        <div className="grid grid-cols-2 gap-3 rounded-md bg-gray-50 p-3">
          <Num label="Max jobs / fenêtre" k="max_jobs_per_window" />
          <Num label="Min jobs / fenêtre" k="min_jobs_per_window" />
          <Num label="Profondeur récursion max" k="max_recursion_depth" />
          <Num label="Max itérations inter-fenêtres" k="max_iterations" />
          <Num label="Epsilon convergence" k="epsilon" step={0.001} />
          <Num label="Rayon de jonction" k="junction_radius" />
          <Num label="k1 (vide = auto)" k="k1" step={0.01} />
          <Num label="k2 (vide = auto)" k="k2" step={0.01} />
        </div>
      )}

      <Button onClick={submit} loading={loading} className="w-full">
        Lancer la résolution
      </Button>
    </div>
  )
}
