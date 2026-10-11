// App.tsx

import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import LoginPage from './auth/LoginPage'
import SetupPage from './auth/SetupPage'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import AlertsPage from './pages/Alerts'
import AboutPage from './pages/About'
import CocktailsPage from './pages/Cocktails'
import Dashboard from './pages/Dashboard'
import Inventory from './pages/Inventory'
import StoreStockPage from './pages/StoreStock'
import ShipmentVerificationsPage from './pages/ShipmentVerifications'
import OrdersPage from './pages/Orders'
import TestLogPage from './pages/TestLog'
import WorklistPage from './pages/Worklist'
import StationPage from './pages/Station'
import ProcessStepsPage from './pages/admin/ProcessSteps'
import PanelDesignerPage from './pages/PanelDesigner'
import AntibodiesPage from './pages/admin/Antibodies'
import StaffPage from './pages/admin/Staff'
import FluorochromesPage from './pages/admin/Fluorochromes'
import ImportPage from './pages/admin/Import'
import LabSettingsPage from './pages/admin/LabSettings'
import PanelsPage from './pages/admin/Panels'
import SettingsPage from './pages/admin/Settings'
import UsersPage from './pages/admin/Users'
import ValidationPage from './pages/admin/Validation'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()
  if (isLoading) return <Spinner className="min-h-screen" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin, isLoading } = useAuth()
  if (isLoading) return <Spinner className="min-h-screen" />
  if (!isAdmin) return <Navigate to="/" replace />
  return <>{children}</>
}

function RequireService({ children }: { children: React.ReactNode }) {
  const { isService, isLoading } = useAuth()
  if (isLoading) return <Spinner className="min-h-screen" />
  if (!isService) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/setup" element={<SetupPage />} />
      <Route path="/login" element={<LoginPage />} />
      {/* Bench tablet: full screen, outside the sidebar layout */}
      <Route path="/station" element={<RequireAuth><StationPage /></RequireAuth>} />

      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="inventory" element={<Inventory />} />
        <Route path="store" element={<StoreStockPage />} />
        <Route path="shipment-qc" element={<ShipmentVerificationsPage />} />
        <Route path="cocktails" element={<CocktailsPage />} />
        <Route path="tests" element={<TestLogPage />} />
        <Route path="worklist" element={<WorklistPage />} />
        <Route path="designer" element={<PanelDesignerPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="about" element={<AboutPage />} />

        {/* Admin-only routes */}
        <Route
          path="admin/import"
          element={<RequireAdmin><ImportPage /></RequireAdmin>}
        />
        <Route
          path="admin/lab-settings"
          element={<RequireAdmin><LabSettingsPage /></RequireAdmin>}
        />
        <Route
          path="admin/fluorochromes"
          element={<RequireAdmin><FluorochromesPage /></RequireAdmin>}
        />
        <Route
          path="admin/panels"
          element={<RequireAdmin><PanelsPage /></RequireAdmin>}
        />
        <Route
          path="admin/antibodies"
          element={<RequireAdmin><AntibodiesPage /></RequireAdmin>}
        />
        <Route
          path="admin/users"
          element={<RequireAdmin><UsersPage /></RequireAdmin>}
        />
        <Route
          path="admin/process-steps"
          element={<RequireAdmin><ProcessStepsPage /></RequireAdmin>}
        />
        <Route
          path="admin/staff"
          element={<RequireAdmin><StaffPage /></RequireAdmin>}
        />
        <Route
          path="admin/settings"
          element={<RequireAdmin><SettingsPage /></RequireAdmin>}
        />
        <Route
          path="admin/validation"
          element={<RequireService><ValidationPage /></RequireService>}
        />
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
