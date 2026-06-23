import GanttBar from './GanttBar'
import SetupBar from './SetupBar'

export default function GanttRow({ machine, entries, zoom, rowHeight, width, selectedJobId, onSelect }) {
  return (
    <div className="flex border-b border-gray-100">
      <div
        className="sticky left-0 z-10 flex shrink-0 items-center bg-white px-3 text-xs font-medium text-gray-600"
        style={{ width: 120, height: rowHeight }}
      >
        {machine.external_id}
      </div>
      <div className="relative" style={{ width, height: rowHeight }}>
        {entries.map((e, i) => (
          <div key={i}>
            <SetupBar setup={e.setup} zoom={zoom} rowHeight={rowHeight} />
            <GanttBar
              entry={e}
              zoom={zoom}
              rowHeight={rowHeight}
              selected={selectedJobId === e.job_id}
              onSelect={onSelect}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
