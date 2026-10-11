// auth/AuthContext.tsx

import React, { createContext, useContext, useEffect, useState } from 'react'
import { authApi } from '../api/client'
import type { User } from '../types'

interface AuthState {
  user: User | null
  token: string | null
  isAdmin: boolean
  isService: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Rehydrate from localStorage on mount
  useEffect(() => {
    const storedToken = localStorage.getItem('flowjai_token')
    const storedUser = localStorage.getItem('flowjai_user')
    if (storedToken && storedUser) {
      try {
        setToken(storedToken)
        setUser(JSON.parse(storedUser))
      } catch {
        localStorage.removeItem('flowjai_token')
        localStorage.removeItem('flowjai_user')
      }
    }
    setIsLoading(false)
  }, [])

  const login = async (username: string, password: string) => {
    const tokenData = await authApi.login(username, password)
    localStorage.setItem('flowjai_token', tokenData.access_token)
    setToken(tokenData.access_token)

    const me = await authApi.me()
    localStorage.setItem('flowjai_user', JSON.stringify(me))
    setUser(me)
  }

  const logout = () => {
    localStorage.removeItem('flowjai_token')
    localStorage.removeItem('flowjai_user')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAdmin: user?.role === 'admin' || user?.role === 'service',
        isService: user?.role === 'service',
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
