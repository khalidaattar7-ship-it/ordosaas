export default function SetupBar({ setup, zoom, rowHeight }) {
  if (!setup || !setup.duration) return null
  return (
    <div
      title={`Setup depuis ${setup.from_job_external_id} (${setup.duration})`}
      className="absolute top-1/2 -translate-y-1/2 rounded-sm"
      style={{
        left: setup.start_time * zoom,
        width: Math.max(2, setup.duration * zoom),
        height: rowHeight * 0.5,
        backgroundColor: '#9ca3af',
        backgroundImage:
          'repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(255,255,255,0.4) 3px, rgba(255,255,255,0.4) 6px)',
      }}
    />
  )
}
