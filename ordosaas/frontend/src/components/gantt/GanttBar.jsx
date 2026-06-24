export default function GanttBar({ entry, zoom, rowHeight, selected, onSelect }) {
  const color = entry.is_late ? '#C84848' : '#2A7A5B'
  const tooltip = `${entry.job_external_id} • ${entry.machine_external_id}\n${entry.start_time} → ${entry.end_time} (durée ${entry.duration})${
    entry.job_tardiness ? `\nretard: ${entry.job_tardiness}` : ''
  }`
  return (
    <div
      title={tooltip}
      onClick={() => onSelect?.(entry)}
      className="absolute top-1/2 flex -translate-y-1/2 cursor-pointer items-center justify-center overflow-hidden rounded text-[10px] font-medium text-white"
      style={{
        left: entry.start_time * zoom,
        width: Math.max(3, entry.duration * zoom),
        height: rowHeight * 0.66,
        backgroundColor: color,
        outline: selected ? '2px solid #1e293b' : 'none',
        zIndex: selected ? 5 : 2,
      }}
    >
      {entry.duration * zoom > 24 && entry.job_external_id}
    </div>
  )
}
