import clsx from 'clsx'

import LoadingSpinner from './LoadingSpinner'

export default function Table({ columns, data, loading, pagination, onPageChange, emptyLabel }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-100 bg-white">
      <table className="min-w-full divide-y divide-gray-100 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className="px-4 py-3 text-left font-medium text-gray-500 whitespace-nowrap"
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {loading && (
            <tr>
              <td colSpan={columns.length}>
                <LoadingSpinner label="Chargement..." />
              </td>
            </tr>
          )}
          {!loading && (!data || data.length === 0) && (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-400">
                {emptyLabel || 'Aucune donnée'}
              </td>
            </tr>
          )}
          {!loading &&
            data?.map((row, i) => (
              <tr key={row.id || i} className="hover:bg-gray-50">
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3 text-gray-700 whitespace-nowrap">
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>

      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-between border-t border-gray-100 px-4 py-3 text-sm text-gray-500">
          <span>
            Page {pagination.page} / {pagination.total_pages} — {pagination.total} éléments
          </span>
          <div className="flex gap-2">
            <button
              className="rounded border border-gray-200 px-3 py-1 disabled:opacity-40"
              disabled={pagination.page <= 1}
              onClick={() => onPageChange(pagination.page - 1)}
            >
              Précédent
            </button>
            <button
              className={clsx(
                'rounded border border-gray-200 px-3 py-1',
                pagination.page >= pagination.total_pages && 'opacity-40',
              )}
              disabled={pagination.page >= pagination.total_pages}
              onClick={() => onPageChange(pagination.page + 1)}
            >
              Suivant
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
