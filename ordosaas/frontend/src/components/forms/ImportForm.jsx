import { FileCheck2, UploadCloud } from 'lucide-react'
import { useState } from 'react'
import { useDropzone } from 'react-dropzone'

import { importInstance } from '../../api/instances'
import Button from '../common/Button'

function DropZone({ label, file, onFile, optional }) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { 'text/csv': ['.csv'] },
    multiple: false,
    onDrop: (accepted) => accepted[0] && onFile(accepted[0]),
  })
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">
        {label} {optional && <span className="text-gray-400">(optionnel)</span>}
      </label>
      <div
        {...getRootProps()}
        className={`flex cursor-pointer flex-col items-center gap-1 rounded-md border-2 border-dashed px-4 py-5 text-sm ${
          isDragActive ? 'border-accent bg-blue-50' : 'border-gray-200'
        }`}
      >
        <input {...getInputProps()} />
        {file ? (
          <span className="flex items-center gap-2 text-green-600">
            <FileCheck2 className="h-4 w-4" /> {file.name}
          </span>
        ) : (
          <span className="flex items-center gap-2 text-gray-400">
            <UploadCloud className="h-4 w-4" /> Glissez un fichier .csv
          </span>
        )}
      </div>
    </div>
  )
}

export default function ImportForm({ onSuccess }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [jobsFile, setJobsFile] = useState(null)
  const [opsFile, setOpsFile] = useState(null)
  const [setupsFile, setSetupsFile] = useState(null)
  const [error, setError] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    setError(null)
    setWarnings([])
    if (!name || !jobsFile || !opsFile) {
      setError('Nom, jobs.csv et operations.csv sont obligatoires.')
      return
    }
    const fd = new FormData()
    fd.append('name', name)
    if (description) fd.append('description', description)
    fd.append('jobs_file', jobsFile)
    fd.append('operations_file', opsFile)
    if (setupsFile) fd.append('setups_file', setupsFile)

    setLoading(true)
    try {
      const res = await importInstance(fd)
      setWarnings(res.validation_warnings || [])
      onSuccess?.(res)
    } catch (err) {
      setError(err.message || "Échec de l'import")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">Nom de l'instance</label>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">Description</label>
        <input
          className="input"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <DropZone label="jobs.csv" file={jobsFile} onFile={setJobsFile} />
      <DropZone label="operations.csv" file={opsFile} onFile={setOpsFile} />
      <DropZone label="setups.csv" file={setupsFile} onFile={setSetupsFile} optional />

      {error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      {warnings.length > 0 && (
        <div className="space-y-1 rounded bg-orange-50 px-3 py-2 text-sm text-orange-700">
          {warnings.map((w, i) => (
            <div key={i}>⚠ {w.message}</div>
          ))}
        </div>
      )}

      <Button onClick={submit} loading={loading} className="w-full">
        Importer
      </Button>
    </div>
  )
}
