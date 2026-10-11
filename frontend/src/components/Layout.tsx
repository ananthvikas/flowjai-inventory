// components/Layout.tsx

import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  LayoutDashboard, Package, Warehouse, FlaskConical, ClipboardList,
  Bell, ShoppingCart, Settings, Users, LogOut, Microscope, Droplets, Info,
  BarChart2, FileUp, ListChecks, Contact, PackageCheck, Tablet, Workflow,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { alertsApi, labSettingsApi, shipmentVerificationsApi } from '../api/client'

export default function Layout() {
  const { user, isAdmin, isService, logout } = useAuth()
  const navigate = useNavigate()

  const { data: alerts = [] } = useQuery({
    queryKey: ['alerts', 'unread-count'],
    queryFn: () => alertsApi.list(true),
    refetchInterval: 60_000,
  })

  const { data: shipmentQc } = useQuery({
    queryKey: ['shipment-verifications', 'summary'],
    queryFn: shipmentVerificationsApi.summary,
    refetchInterval: 60_000,
  })

  const { data: labSettings } = useQuery({
    queryKey: ['lab-settings'],
    queryFn: labSettingsApi.get,
    staleTime: 300_000,
  })

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navItems = [
    { to: '/',           icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/inventory',  icon: Package,         label: 'Inventory' },
    { to: '/store',      icon: Warehouse,       label: 'Store Stock' },
    { to: '/shipment-qc', icon: PackageCheck,   label: 'Shipment QC', badge: shipmentQc?.open ?? 0, badgeUrgent: (shipmentQc?.overdue ?? 0) > 0 },
    { to: '/cocktails',  icon: FlaskConical,    label: 'Cocktails' },
    { to: '/tests',      icon: ClipboardList,   label: 'Test Log' },
    { to: '/worklist',   icon: ListChecks,      label: 'Worklist' },
    { to: '/station',    icon: Tablet,          label: 'Bench station' },
    { to: '/designer',   icon: Microscope,      label: 'Panel Designer' },
    { to: '/alerts',     icon: Bell,            label: 'Alerts', badge: alerts.length },
    { to: '/orders',     icon: ShoppingCart,    label: 'Orders' },
    { to: '/about',      icon: Info,            label: 'About' },
  ]

  const adminItems = [
    { to: '/admin/import',        icon: FileUp,       label: 'Antibody import' },
    { to: '/admin/lab-settings',  icon: Settings,     label: 'Lab Settings' },
    { to: '/admin/fluorochromes', icon: Droplets,     label: 'Fluorochromes' },
    { to: '/admin/panels',        icon: FlaskConical, label: 'Panels' },
    { to: '/admin/antibodies',    icon: Microscope,   label: 'Antibodies' },
    { to: '/admin/users',         icon: Users,        label: 'Users' },
    { to: '/admin/staff',         icon: Contact,      label: 'Staff' },
    { to: '/admin/process-steps', icon: Workflow,     label: 'Processing steps' },
    { to: '/admin/settings',      icon: Settings,     label: 'Alert Rules' },
  ]

  const serviceItems = [
    { to: '/admin/validation',    icon: BarChart2,    label: 'Validation' },
  ]

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* ── Sidebar ── */}
      <aside className="w-56 shrink-0 flex flex-col bg-brand-900 text-white">
        {/* Logo + Lab Name */}
        <div className="px-4 py-4 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-white/15 flex items-center justify-center shrink-0">
              <Microscope className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-white leading-none">FlowJAI</p>
              <p className="text-xs text-white/45 leading-none mt-0.5">Inventory Manager</p>
            </div>
          </div>
          {labSettings?.lab_name && (
            <div className="mt-2.5 bg-white/10 rounded-lg px-2.5 py-1.5">
              <p className="text-xs font-semibold text-white leading-tight truncate">
                {labSettings.lab_name}
              </p>
              {labSettings.lab_subtitle && (
                <p className="text-xs text-white/50 leading-tight truncate mt-0.5">
                  {labSettings.lab_subtitle}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {navItems.map(({ to, icon: Icon, label, badge, badgeUrgent }: { to: string; icon: typeof Bell; label: string; badge?: number; badgeUrgent?: boolean }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-white/15 text-white font-medium'
                    : 'text-white/65 hover:bg-white/10 hover:text-white',
                )
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className="flex-1">{label}</span>
              {badge != null && badge > 0 && (
                <span
                  className={clsx(
                    'text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[1.25rem] text-center',
                    label === 'Shipment QC' && !badgeUrgent ? 'bg-amber-500' : 'bg-red-500',
                  )}
                  title={label === 'Shipment QC' ? (badgeUrgent ? 'Open verifications — some overdue' : 'Open verifications') : undefined}
                >
                  {badge > 99 ? '99+' : badge}
                </span>
              )}
            </NavLink>
          ))}

          {isAdmin && (
            <>
              <div className="px-3 pt-4 pb-1">
                <p className="text-xs font-semibold text-white/35 uppercase tracking-wider">
                  Admin
                </p>
              </div>
              {adminItems.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                      isActive
                        ? 'bg-white/15 text-white font-medium'
                        : 'text-white/65 hover:bg-white/10 hover:text-white',
                    )
                  }
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  {label}
                </NavLink>
              ))}
            </>
          )}

          {isService && (
            <>
              <div className="px-3 pt-4 pb-1">
                <p className="text-xs font-semibold text-white/35 uppercase tracking-wider">
                  Validation
                </p>
              </div>
              {serviceItems.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                      isActive
                        ? 'bg-white/15 text-white font-medium'
                        : 'text-white/65 hover:bg-white/10 hover:text-white',
                    )
                  }
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  {label}
                </NavLink>
              ))}
            </>
          )}
        </nav>

        {/* User footer */}
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
            <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center text-xs font-bold shrink-0">
              {user?.username[0].toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user?.username}</p>
              <p className="text-xs text-white/45 capitalize">{user?.role}</p>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              className="text-white/45 hover:text-white transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
