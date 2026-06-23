import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/layout/Layout'
import { useAuth } from './hooks/useAuth'
import AuditLogs from './pages/AuditLogs'
import Dashboard from './pages/Dashboard'
import InstanceDetail from './pages/InstanceDetail'
import Instances from './pages/Instances'
import Login from './pages/Login'
import Machines from './pages/Machines'
import ResolutionDetail from './pages/ResolutionDetail'
import Settings from './pages/Settings'
import Users from './pages/Users'

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/instances" element={<Instances />} />
        <Route path="/instances/:id" element={<InstanceDetail />} />
        <Route path="/resolutions/:id" element={<ResolutionDetail />} />
        <Route path="/machines" element={<Machines />} />
        <Route path="/users" element={<Users />} />
        <Route path="/audit" element={<AuditLogs />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
