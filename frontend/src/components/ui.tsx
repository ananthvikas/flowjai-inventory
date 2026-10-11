// components/ui.tsx — minimal shared primitives (no external UI library needed)

import { clsx } from 'clsx'
import React from 'react'

// ── Badge ───────────────────────────────────────────────────────────────────

const badgeVariants = {
  ok:       'bg-emerald-100 text-emerald-800 border-emerald-200',
  warning:  'bg-amber-100  text-amber-800  border-amber-200',
  critical: 'bg-red-100    text-red-800    border-red-200',
  unknown:  'bg-slate-100  text-slate-600  border-slate-200',
  info:     'bg-blue-100   text-blue-800   border-blue-200',
  pending:  'bg-amber-100  text-amber-800  border-amber-200',
  delivered:'bg-emerald-100 text-emerald-800 border-emerald-200',
  cancelled:'bg-slate-100  text-slate-500  border-slate-200',
}

type BadgeVariant = keyof typeof badgeVariants

export function Badge({
  variant = 'info',
  children,
  className,
}: {
  variant?: BadgeVariant
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border',
        badgeVariants[variant],
        className,
      )}
    >
      {children}
    </span>
  )
}

// ── Button ──────────────────────────────────────────────────────────────────

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
type ButtonSize    = 'sm' | 'md'

const btnBase = 'inline-flex items-center gap-1.5 font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed'
const btnVariants: Record<ButtonVariant, string> = {
  primary:   'bg-brand-600 text-white hover:bg-brand-700 focus:ring-brand-500',
  secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 focus:ring-brand-500',
  danger:    'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  ghost:     'text-slate-600 hover:bg-slate-100 focus:ring-slate-300',
}
const btnSizes: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-xs',
  md: 'px-4    py-2   text-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
}) {
  return (
    <button
      className={clsx(btnBase, btnVariants[variant], btnSizes[size], className)}
      {...props}
    >
      {children}
    </button>
  )
}

// ── Card ────────────────────────────────────────────────────────────────────

export function Card({
  children,
  className,
  padding = true,
}: {
  children: React.ReactNode
  className?: string
  padding?: boolean
}) {
  return (
    <div
      className={clsx(
        'bg-white rounded-xl border border-slate-200 shadow-sm',
        padding && 'p-5',
        className,
      )}
    >
      {children}
    </div>
  )
}

// ── Input ───────────────────────────────────────────────────────────────────

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & { label?: string; error?: string }
>(({ label, error, className, ...props }, ref) => (
  <div className="flex flex-col gap-1">
    {label && (
      <label className="text-sm font-medium text-slate-700">{label}</label>
    )}
    <input
      ref={ref}
      className={clsx(
        'px-3.5 py-2 text-sm border rounded-lg transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent',
        error ? 'border-red-400' : 'border-slate-300',
        className,
      )}
      {...props}
    />
    {error && <p className="text-xs text-red-600">{error}</p>}
  </div>
))
Input.displayName = 'Input'

// ── Select ──────────────────────────────────────────────────────────────────

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }
>(({ label, className, children, ...props }, ref) => (
  <div className="flex flex-col gap-1">
    {label && <label className="text-sm font-medium text-slate-700">{label}</label>}
    <select
      ref={ref}
      className={clsx(
        'px-3.5 py-2 text-sm border border-slate-300 rounded-lg bg-white',
        'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  </div>
))
Select.displayName = 'Select'

// ── Modal ───────────────────────────────────────────────────────────────────

export function Modal({
  open,
  onClose,
  title,
  children,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  size?: 'md' | 'lg' | 'xl'
}) {
  if (!open) return null
  const width = size === 'xl' ? 'max-w-4xl' : size === 'lg' ? 'max-w-2xl' : 'max-w-md'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className={clsx('relative bg-white rounded-2xl shadow-xl w-full max-h-[90vh] overflow-y-auto', width)}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 transition-colors"
          >
            ✕
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

// ── Spinner ──────────────────────────────────────────────────────────────────

export function Spinner({ className }: { className?: string }) {
  return (
    <div className={clsx('flex items-center justify-center', className)}>
      <div className="w-6 h-6 border-2 border-slate-200 border-t-brand-600 rounded-full animate-spin" />
    </div>
  )
}

// ── Stat card ────────────────────────────────────────────────────────────────

export function StatCard({
  label,
  value,
  sub,
  icon,
  color = 'blue',
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ReactNode
  color?: 'blue' | 'green' | 'amber' | 'red'
}) {
  const colors = {
    blue:  'bg-blue-50  text-blue-600',
    green: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    red:   'bg-red-50   text-red-600',
  }
  return (
    <Card className="flex items-center gap-4">
      <div className={clsx('w-11 h-11 rounded-xl flex items-center justify-center shrink-0', colors[color])}>
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-900 leading-none">{value}</p>
        <p className="text-sm text-slate-500 mt-0.5">{label}</p>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </Card>
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-slate-400">
      <div className="text-4xl mb-3">📭</div>
      <p className="text-sm">{message}</p>
    </div>
  )
}
