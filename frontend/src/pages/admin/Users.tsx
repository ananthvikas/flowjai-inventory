// pages/admin/Users.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { usersApi } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../../components/ui'
import type { User } from '../../types'

// ── Create User Modal ───────────────────────────────────────────────────────

function CreateUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ username: '', email: '', password: '', role: 'technologist' })
  const [error, setError] = useState('')
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const mut = useMutation({
    mutationFn: () => usersApi.create({
      username: form.username,
      email: form.email || undefined,
      password: form.password,
      role: form.role,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      onClose()
      setForm({ username: '', email: '', password: '', role: 'technologist' })
      setError('')
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error creating user'),
  })

  return (
    <Modal open={open} onClose={onClose} title="New User">
      <div className="space-y-4">
        <Input
          label="Username"
          value={form.username}
          onChange={e => set('username', e.target.value)}
          placeholder="e.g. jsmith"
          autoFocus
        />
        <Input
          label="Email (optional)"
          type="email"
          value={form.email}
          onChange={e => set('email', e.target.value)}
          placeholder="j.smith@hospital.org"
        />
        <Input
          label="Password"
          type="password"
          value={form.password}
          onChange={e => set('password', e.target.value)}
          placeholder="Minimum 8 characters"
        />
        <Select label="Role" value={form.role} onChange={e => set('role', e.target.value)}>
          <option value="technologist">Technologist</option>
          <option value="admin">Admin</option>
          <option value="service">Service</option>
        </Select>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => mut.mutate()}
            disabled={mut.isPending || !form.username || !form.password}
          >
            {mut.isPending ? 'Creating...' : 'Create user'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Edit User Modal ─────────────────────────────────────────────────────────

function EditUserModal({ user, onClose }: { user: User | null; onClose: () => void }) {
  const qc = useQueryClient()
  const { user: me } = useAuth()

  const [form, setForm] = useState({
    username: user?.username ?? '',
    email:    user?.email    ?? '',
    role:     user?.role     ?? 'technologist',
  })
  const [newPassword, setNewPassword]   = useState('')
  const [confirmPwd,  setConfirmPwd]    = useState('')
  const [error,       setError]         = useState('')
  const [pwdError,    setPwdError]      = useState('')
  const [pwdOk,       setPwdOk]         = useState(false)
  const set = (k: string, v: string) => { setForm(f => ({ ...f, [k]: v })); setError('') }

  const isSelf = user?.id === me?.id

  const updateMut = useMutation({
    mutationFn: () => usersApi.update(user!.id, {
      username: form.username || undefined,
      email:    form.email    || undefined,
      role:     form.role,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error updating user'),
  })

  const resetPwdMut = useMutation({
    mutationFn: () => usersApi.adminResetPassword(user!.id, newPassword),
    onSuccess: () => {
      setPwdOk(true)
      setNewPassword('')
      setConfirmPwd('')
      setTimeout(() => setPwdOk(false), 3000)
    },
    onError: (e: any) => setPwdError(e.response?.data?.detail ?? 'Error resetting password'),
  })

  const handleResetPassword = () => {
    setPwdError('')
    if (newPassword.length < 4) { setPwdError('Password too short'); return }
    if (newPassword !== confirmPwd) { setPwdError('Passwords do not match'); return }
    resetPwdMut.mutate()
  }

  if (!user) return null

  return (
    <Modal open={!!user} onClose={onClose} title={`Edit user — ${user.username}`}>
      <div className="space-y-5">

        {/* ── Details section ── */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Details</p>
          <Input
            label="Username"
            value={form.username}
            onChange={e => set('username', e.target.value)}
          />
          <Input
            label="Email (optional)"
            type="email"
            value={form.email}
            onChange={e => set('email', e.target.value)}
            placeholder="Leave blank if not needed"
          />
          <Select
            label="Role"
            value={form.role}
            onChange={e => set('role', e.target.value)}
            disabled={isSelf}  // can't demote yourself
          >
            <option value="technologist">Technologist</option>
            <option value="admin">Admin</option>
            <option value="service">Service</option>
          </Select>
          {isSelf && (
            <p className="text-xs text-slate-400">You cannot change your own role.</p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end">
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending || !form.username}>
              {updateMut.isPending ? 'Saving...' : 'Save details'}
            </Button>
          </div>
        </div>

        <hr className="border-slate-100" />

        {/* ── Password reset section ── */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Reset password
          </p>
          <Input
            label="New password"
            type="password"
            value={newPassword}
            onChange={e => { setNewPassword(e.target.value); setPwdError(''); setPwdOk(false) }}
            placeholder="Enter new password"
          />
          <Input
            label="Confirm password"
            type="password"
            value={confirmPwd}
            onChange={e => { setConfirmPwd(e.target.value); setPwdError(''); setPwdOk(false) }}
            placeholder="Repeat new password"
            error={confirmPwd && newPassword !== confirmPwd ? 'Passwords do not match' : undefined}
          />
          {pwdError && <p className="text-sm text-red-600">{pwdError}</p>}
          {pwdOk    && <p className="text-sm text-emerald-600 font-medium">Password reset successfully</p>}
          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={handleResetPassword}
              disabled={resetPwdMut.isPending || !newPassword || !confirmPwd}
            >
              {resetPwdMut.isPending ? 'Resetting...' : 'Reset password'}
            </Button>
          </div>
        </div>

      </div>
    </Modal>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const qc = useQueryClient()
  const { user: me } = useAuth()
  const [createOpen, setCreateOpen] = useState(false)
  const [editUser,   setEditUser]   = useState<User | null>(null)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: usersApi.list,
  })

  const toggleActive = useMutation({
    mutationFn: (u: User) => usersApi.update(u.id, { active: !u.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Users</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage lab staff access</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <UserPlus className="w-4 h-4" /> New user
        </Button>
      </div>

      <Card padding={false}>
        {isLoading ? (
          <Spinner className="py-16" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['Username', 'Email', 'Role', 'Status', ''].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.length === 0 && (
                <tr><td colSpan={5}><EmptyState message="No users" /></td></tr>
              )}
              {users.map(u => (
                <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-800">
                    {u.username}
                    {u.id === me?.id && (
                      <span className="text-xs text-slate-400 ml-1.5">(you)</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {u.email ?? <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={u.role === 'admin' ? 'critical' : 'info'}>
                      {u.role}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={u.active ? 'ok' : 'unknown'}>
                      {u.active ? 'Active' : 'Inactive'}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1.5">
                      <Button variant="ghost" size="sm" onClick={() => setEditUser(u)}>
                        <Pencil className="w-3.5 h-3.5" /> Edit
                      </Button>
                      {u.id !== me?.id && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleActive.mutate(u)}
                          className={u.active ? 'text-red-400 hover:text-red-600 hover:bg-red-50' : ''}
                        >
                          {u.active ? 'Disable' : 'Enable'}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <CreateUserModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <EditUserModal user={editUser} onClose={() => setEditUser(null)} />
    </div>
  )
}
