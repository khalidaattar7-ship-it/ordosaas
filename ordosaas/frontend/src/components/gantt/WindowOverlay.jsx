export default function WindowOverlay({ windows, zoom, height }) {
  if (!windows?.length) return null
  return (
    <>
      {windows.map((w, i) => (
        <div
          key={w.window_index}
          title={`Fenêtre ${w.window_index} (${w.nb_jobs} jobs, ${w.status})`}
          className="pointer-events-none absolute top-0"
          style={{
            left: w.t_start * zoom,
            width: Math.max(1, (w.t_end - w.t_start) * zoom),
            height,
            backgroundColor: i % 2 === 0 ? 'rgba(196,150,58,0.05)' : 'rgba(196,150,58,0.11)',
            borderLeft: '1px dashed rgba(196,150,58,0.45)',
          }}
        />
      ))}
    </>
  )
}
