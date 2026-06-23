import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { useState } from 'react'

import { listAuditLogs } from '../api/tenant'
import Table from '../components/common/Table'

export default function AuditLogs() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['audit', page],
    queryFn: () => listAuditLogs({ page, per_page: 50 }),
  })

  const columns = [
    {
      key: 'created_at',
      label: 'Date',
      render: (r) => format(new Date(r.created_at), 'dd/MM/yyyy HH:mm:ss'),
    },
    { key: 'action', label: 'Action', render: (r) => <span className="font-medium">{r.action}</span> },
    { key: 'resource_type', label: 'Ressource', render: (r) => r.resource_type || '—' },
    { key: 'user_id', label: 'Utilisateur', render: (r) => r.user_id || '—' },
    { key: 'ip', label: 'IP', render: (r) => r.ip || '—' },
  ]

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-gray-800">Journaux d'audit</h1>
      <Table
        columns={columns}
        data={data?.data}
        loading={isLoading}
        pagination={data?.pagination}
        onPageChange={setPage}
        emptyLabel="Aucun journal"
      />
    </div>
  )
}
